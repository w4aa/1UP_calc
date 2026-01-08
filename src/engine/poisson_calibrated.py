
from .base import fit_lambda_from_ou_lines
"""
Calibrated Poisson Engine with Underdog Correction

This engine addresses the systematic bias in 1UP probability calculation
for underdogs. The standard Poisson model overestimates underdog 1UP probability
because it doesn't account for:

1. The correlation between scoring frequency and lead maintenance
2. Real-world "upset factors" that are already priced into markets
3. The asymmetric impact of lambda imbalance on 1UP outcomes

Solution: Apply empirically-derived correction factors based on lambda ratio.

MAJOR UPDATES - 2026-01-08
==========================

VERSION 1 (Initial Fix):
- Fixed double correction bug (lambdas + probabilities -> probabilities only)
- Aggressive corrections based on pre-bug analysis
- Results: Underdog bias eliminated (-95%), but overcorrected balanced matches

VERSION 2 (Refined - Current):
- Gentler corrections for ratio < 1.6 (was causing underpricing in v1)
- Reduced favorite correction by ~30% (was too aggressive in v1)
- More aggressive for extreme ratios >3.2 (0.70-0.75 vs v1's 0.75-0.82)
- Start corrections earlier (1.05/1.1 vs 1.15) with minimal impact

V2 CORRECTION RANGES:
- Underdog: 0.70-1.00 (gentle for <1.6, aggressive for >3.2)
- Favorite: 0.94-1.00 (30% less aggressive than v1)

See ENGINE_ANALYSIS.md and CALIBRATION_RESULTS.md for full details.
"""

import math
from typing import Optional, Tuple
from .base import (
    BaseEngine,
    devig_three_way,
    infer_lambda_from_ou_market,
    simulate_1up_probabilities,
)
import numpy as np


def calculate_lambda_ratio(lambda_home: float, lambda_away: float) -> Tuple[float, bool, bool]:
    """
    Calculate lambda ratio and identify underdog.
    
    Returns:
        Tuple of (ratio, home_is_underdog, away_is_underdog)
        ratio is always >= 1.0 (stronger / weaker)
    """
    if lambda_home < 0.01 or lambda_away < 0.01:
        return 1.0, False, False
    
    if lambda_home < lambda_away:
        return lambda_away / lambda_home, True, False
    elif lambda_away < lambda_home:
        return lambda_home / lambda_away, False, True
    else:
        return 1.0, False, False


def get_underdog_correction(ratio: float) -> float:
    """
    Get the probability correction factor for underdog based on lambda ratio.

    VERSION 2 - 2026-01-08: Refined after v1 testing on 117 matches.

    V1 RESULTS ANALYSIS:
    - Balanced <1.15 (14 matches): Underdog MAE increased 7.7% (was overcorrected)
    - Slight 1.15-1.5 (36 matches): Underdog MAE increased 41.4% (too aggressive)
    - Moderate 1.5-2.0 (35 matches): Underdog MAE improved 16.6% ✓
    - High 2.0-3.0 (24 matches): Underdog MAE improved 49.9% ✓✓
    - Extreme >3.0 (8 matches): Underdog MAE worsened 8.4% (need more aggression)

    V2 CHANGES:
    - Gentler correction for ratio < 1.6 (was causing underpricing)
    - Start correction earlier (1.05 vs 1.15) with minimal impact
    - More aggressive for extreme ratios >3.2 (0.70-0.75 vs 0.75-0.82)

    The correction REDUCES the underdog's 1UP probability to match market.
    """
    if ratio <= 1.0:
        return 1.0

    # V2: Refined piecewise linear with gentler low-ratio corrections
    if ratio <= 1.05:
        # Very balanced: no correction
        return 1.0
    elif ratio <= 1.3:
        # Balanced to slight: very gentle correction (1.00 -> 0.985)
        # V1 had no correction until 1.15, causing underpricing
        return 1.0 - 0.015 * (ratio - 1.05) / 0.25
    elif ratio <= 1.6:
        # Slight imbalance: light correction (0.985 -> 0.955)
        # V1 was too aggressive (0.97-1.00), causing 41% error increase
        return 0.985 - 0.03 * (ratio - 1.3) / 0.30
    elif ratio <= 2.2:
        # Moderate: standard correction (0.955 -> 0.90)
        # V1 worked well here
        return 0.955 - 0.055 * (ratio - 1.6) / 0.6
    elif ratio <= 3.2:
        # High: strong correction (0.90 -> 0.80)
        # V1 worked very well (-50% error), keep similar
        return 0.90 - 0.10 * (ratio - 2.2) / 1.0
    else:
        # Extreme: very aggressive correction (0.80 -> 0.70)
        # V1 insufficient (0.75-0.82), need more aggression
        ratio_scaled = min((ratio - 3.2) / 2.5, 1.0)
        return 0.80 - 0.10 * ratio_scaled


def get_favorite_correction(ratio: float) -> float:
    """
    Get the probability correction factor for favorite based on lambda ratio.

    VERSION 2 - 2026-01-08: Reduced strength by ~30% after v1 testing.

    V1 RESULTS ANALYSIS:
    - ALL ratio bins showed favorite MAE increase of +20% to +48%
    - Favorites were being UNDERPRICED across the board
    - V1 correction was too aggressive (0.90-1.00 range)

    V2 CHANGES:
    - Reduce correction strength by ~30% across all ratios
    - Gentler correction: 0.94-1.00 vs V1's 0.90-1.00
    - Start correction at 1.1 (vs 1.15) to catch more cases

    Markets are tighter than model predicts, but V1 overcorrected.
    """
    if ratio <= 1.0:
        return 1.0

    if ratio <= 1.1:
        # Very balanced: NO correction
        return 1.0
    elif ratio <= 2.0:
        # Balanced to moderate: gentle correction (1.00 -> 0.98)
        # V1 was 0.97, too aggressive
        return 1.0 - 0.02 * (ratio - 1.1) / 0.9
    else:
        # High imbalance: stronger but still gentle (0.98 -> 0.94)
        # V1 was 0.90-0.97, way too aggressive
        return 0.98 - 0.04 * min((ratio - 2.0) / 2.5, 1.0)


def correct_1up_probabilities(
    p_home: float, 
    p_away: float, 
    lambda_home: float, 
    lambda_away: float
) -> Tuple[float, float]:
    """
    Apply empirical corrections to 1UP probabilities.
    
    Args:
        p_home: Raw P(Home 1UP) from simulation
        p_away: Raw P(Away 1UP) from simulation
        lambda_home: Home team's expected goals
        lambda_away: Away team's expected goals
    
    Returns:
        Tuple of (corrected_p_home, corrected_p_away)
    """
    ratio, home_is_underdog, away_is_underdog = calculate_lambda_ratio(lambda_home, lambda_away)
    
    if home_is_underdog:
        # Home is underdog, away is favorite
        underdog_corr = get_underdog_correction(ratio)
        favorite_corr = get_favorite_correction(ratio)
        p_home_corr = p_home * underdog_corr
        p_away_corr = p_away * favorite_corr
    elif away_is_underdog:
        # Away is underdog, home is favorite
        underdog_corr = get_underdog_correction(ratio)
        favorite_corr = get_favorite_correction(ratio)
        p_home_corr = p_home * favorite_corr
        p_away_corr = p_away * underdog_corr
    else:
        # Balanced match
        p_home_corr = p_home
        p_away_corr = p_away
    
    return p_home_corr, p_away_corr


class CalibratedPoissonEngine(BaseEngine):
    """
    Poisson engine with empirical calibration for underdog bias.
    
    This engine applies correction factors to raw Monte Carlo probabilities
    to better match market-implied fair odds, especially for underdogs.
    """
    
    name = "Poisson-Calibrated"
    description = "Poisson model with underdog probability correction"
    
    def __init__(self, n_sims: int = 30000, match_minutes: int = 95, margin_pct: float = 0.05):
        super().__init__(n_sims, match_minutes, margin_pct)
        self.apply_correction = True
    
    def calculate(self, markets: dict, bookmaker: str) -> Optional[dict]:
        """
        Calculate 1UP odds with calibration corrections.
        """
        # Extract required markets
        x1x2 = markets.get('1x2')

        # Support for multi-line O/U: expect lists of (line, over, under) or single tuple
        def ensure_list(val):
            if isinstance(val, list):
                return val
            return [val]

        total_ou = ensure_list(markets.get('total_ou'))
        home_ou = ensure_list(markets.get('home_ou'))
        away_ou = ensure_list(markets.get('away_ou'))

        # Validate required data
        if not all([x1x2, total_ou, home_ou, away_ou]):
            return None

        home_1x2, draw_1x2, away_1x2 = x1x2
        if not all([home_1x2, draw_1x2, away_1x2]):
            return None
        if not all([len(total_ou) > 0, len(home_ou) > 0, len(away_ou) > 0]):
            return None

        # Step 1: De-vig 1X2 for reference
        p_home_win, p_draw, p_away_win = devig_three_way(home_1x2, draw_1x2, away_1x2)

        # Step 2: Infer team lambdas from all available team total markets
        lambda_home_raw = fit_lambda_from_ou_lines(home_ou)
        lambda_away_raw = fit_lambda_from_ou_lines(away_ou)
        split_sum = lambda_home_raw + lambda_away_raw

        # Step 3: Get total expected goals from all available total O/U lines
        lambda_total = fit_lambda_from_ou_lines(total_ou)

        if split_sum > 0:
            factor = lambda_total / split_sum
        else:
            factor = 1.0

        lambda_home = lambda_home_raw * factor
        lambda_away = lambda_away_raw * factor

        # Step 3.5: Supremacy optimization (ensure lambda difference matches 1X2-implied supremacy)
        # FIXED 2026-01-08: Removed double correction - correction now applied ONLY to probabilities, not lambdas
        def supremacy_loss(sup):
            l_home = (lambda_total + sup) / 2
            l_away = (lambda_total - sup) / 2
            # Use RAW lambdas (no correction) - correction is applied to probabilities later
            max_goals = 10
            home_win = 0.0
            draw = 0.0
            away_win = 0.0
            for h in range(max_goals+1):
                for a in range(max_goals+1):
                    p = (math.exp(-l_home) * l_home**h / math.factorial(h)) * (math.exp(-l_away) * l_away**a / math.factorial(a))
                    if h > a:
                        home_win += p
                    elif h == a:
                        draw += p
                    else:
                        away_win += p
            return (home_win - p_home_win)**2 + (draw - p_draw)**2 + (away_win - p_away_win)**2
        try:
            from scipy.optimize import minimize_scalar
            res = minimize_scalar(supremacy_loss, bounds=(-2, 2), method='bounded')
            supremacy = res.x if res.success else (lambda_home - lambda_away)
            lambda_home = (lambda_total + supremacy) / 2
            lambda_away = (lambda_total - supremacy) / 2
            # No lambda correction here - correction applied to 1UP probabilities only
        except Exception:
            # Fallback: coarse grid search over sup in [-2,2]
            sups = [x for x in np.linspace(-2.0, 2.0, 201)]
            best_sup = None
            best_loss = float('inf')
            for s in sups:
                val = supremacy_loss(s)
                if val < best_loss:
                    best_loss = val
                    best_sup = s
            if best_sup is not None:
                supremacy = best_sup
                lambda_home = (lambda_total + supremacy) / 2
                lambda_away = (lambda_total - supremacy) / 2
                # No lambda correction here - correction applied to 1UP probabilities only

        # Step 4: Run Monte Carlo simulation for raw 1UP probabilities
        p_home_1up_raw, p_away_1up_raw = simulate_1up_probabilities(
            lambda_home, lambda_away,
            n_sims=self.n_sims,
            match_minutes=self.match_minutes
        )
        
        # Step 5: Apply empirical corrections
        if self.apply_correction:
            p_home_1up, p_away_1up = correct_1up_probabilities(
                p_home_1up_raw, p_away_1up_raw,
                lambda_home, lambda_away
            )
        else:
            p_home_1up = p_home_1up_raw
            p_away_1up = p_away_1up_raw
        
        # Calculate lambda ratio for reporting
        ratio, home_underdog, away_underdog = calculate_lambda_ratio(lambda_home, lambda_away)
        
        # Build result
        return self._build_result(
            lambda_home=lambda_home,
            lambda_away=lambda_away,
            lambda_total=lambda_total,
            p_home_1up=p_home_1up,
            p_away_1up=p_away_1up,
            draw_odds=draw_1x2,
            input_1x2={'home': home_1x2, 'draw': draw_1x2, 'away': away_1x2},
            extra={
                'p_home_win': p_home_win,
                'p_draw': p_draw,
                'p_away_win': p_away_win,
                    'p_home_1up_raw': p_home_1up_raw,
                    'p_away_1up_raw': p_away_1up_raw,
                    'lambda_ratio': ratio,
                    'correction_applied': self.apply_correction,
            }
        )
