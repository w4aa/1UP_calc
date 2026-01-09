
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

    VERSION 5 - 2026-01-09: CORRECT direction (V4 was inverted disaster).

    V4 DISASTER (117 pawa vs de-vigged):
    - V4 was 48% WORSE than V3 due to INVERTED correction direction
    - Balanced <1.5: -25% to -30% underpricing (V3 was -10%, V4 made it WORSE!)
    - Extreme >3.0: Still +2 to +3 overpricing (not fixed)

    CORRECT LOGIC:
    - LOWER probability → HIGHER odds → Fix underpricing
    - HIGHER probability → LOWER odds → Fix overpricing

    V5 CORRECTIONS:
    - Balanced <1.5: DECREASE prob by 10-13% (increase odds to fix underpricing)
    - Moderate 1.5-2.0: Minimal adjustment (0.87-0.92)
    - High 2.0-3.0: INCREASE prob by 8-30% (decrease odds to fix overpricing)
    - Extreme >3.0: MASSIVE INCREASE prob by 30-80% (slash odds dramatically)

    The correction multiplies raw probability to adjust final odds.
    """
    if ratio <= 1.0:
        return 1.0

    # V5: CORRECT direction
    if ratio <= 1.5:
        # Balanced/Slight: DECREASE probability → INCREASE odds
        # V3 underpriced by 10-12%, so decrease prob by 10-13%
        return 1.0 - 0.13 * (ratio - 1.0) / 0.5
    elif ratio <= 2.0:
        # Moderate: transition (0.87 → 0.92)
        # V3 underpriced by 5-7%, light adjustment
        return 0.87 + 0.05 * (ratio - 1.5) / 0.5
    elif ratio <= 3.0:
        # High: INCREASE probability → DECREASE odds
        # V3 overpriced by 10-20%, increase prob by 8-30%
        return 0.92 + 0.38 * (ratio - 2.0) / 1.0
    else:
        # Extreme: MASSIVE INCREASE → slash odds
        # V3 overpriced by 76-107%, double/triple probability
        ratio_scaled = min((ratio - 3.0) / 3.0, 1.0)
        return 1.30 + 0.50 * ratio_scaled


def get_favorite_correction(ratio: float) -> float:
    """
    Get the probability correction factor for favorite based on lambda ratio.

    VERSION 5 - 2026-01-09: CORRECT direction (V4 was inverted disaster).

    V4 DISASTER (117 pawa matches):
    - V4 INCREASED favorite probability (made underpricing WORSE)
    - Balanced <1.5: -25% to -30% underpricing (V3 was -10%, V4 made it WORSE!)
    - V4 was 48% WORSE than V3 overall

    CORRECT LOGIC:
    - LOWER probability → HIGHER odds → Fix underpricing
    - HIGHER probability → LOWER odds → Fix overpricing

    V5 CORRECTIONS:
    - Balanced <1.5: DECREASE prob by 10% (increase odds to fix underpricing)
    - Moderate 1.5-2.5: Minimal adjustment (0.90-0.95)
    - High >2.5: Continue gentle decrease (favorites less dominant in blowouts)

    The correction multiplies raw probability to adjust final odds.
    """
    if ratio <= 1.0:
        return 1.0

    if ratio <= 1.5:
        # Balanced/Slight: DECREASE probability → INCREASE odds
        # V3 underpriced favorites by 9-10%, so decrease prob by 10%
        return 1.0 - 0.10 * (ratio - 1.0) / 0.5
    elif ratio <= 2.5:
        # Moderate: transition (0.90 → 0.95)
        # Light adjustment as favorites remain underpriced
        return 0.90 + 0.05 * (ratio - 1.5) / 1.0
    else:
        # High/Extreme: gentle decrease (0.95 → 0.92)
        # Favorites in extreme mismatches are less dominant than expected
        return 0.95 - 0.03 * min((ratio - 2.5) / 2.0, 1.0)


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
