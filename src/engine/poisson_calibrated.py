
from .base import fit_lambda_from_ou_lines
# Utility for lambda correction (for use in hybrid engines)
def empirical_underdog_correction(lambda_home: float, lambda_away: float) -> tuple:
    """
    Empirically correct lambdas for underdog bias (used in CalibratedPoissonEngine logic).
    This rescales lambdas so their ratio is less extreme, matching market behavior.
    """
    ratio, home_is_underdog, away_is_underdog = calculate_lambda_ratio(lambda_home, lambda_away)
    # Correction: shrink the ratio toward 1 by a fixed factor (empirical, e.g. 20%)
    if ratio > 1.0:
        shrink = 0.2  # 20% shrink toward 1
        if home_is_underdog:
            new_ratio = 1.0 + (ratio - 1.0) * (1 - shrink)
            lambda_away_new = lambda_home * new_ratio
            return lambda_home, lambda_away_new
        elif away_is_underdog:
            new_ratio = 1.0 + (ratio - 1.0) * (1 - shrink)
            lambda_home_new = lambda_away * new_ratio
            return lambda_home_new, lambda_away
    return lambda_home, lambda_away
"""
Calibrated Poisson Engine with Underdog Correction

This engine addresses the systematic bias in 1UP probability calculation
for underdogs. The standard Poisson model overestimates underdog 1UP probability
because it doesn't account for:

1. The correlation between scoring frequency and lead maintenance
2. Real-world "upset factors" that are already priced into markets
3. The asymmetric impact of lambda imbalance on 1UP outcomes

Solution: Apply empirically-derived correction factors based on lambda ratio.
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
    
    Based on empirical analysis:
    - Balanced (1.0-1.2): ~3% overestimate -> correction 0.97
    - Moderate (1.2-1.8): ~7% overestimate -> correction 0.93
    - High (1.8-2.5): ~10% overestimate -> correction 0.90
    - Extreme (>2.5): ~8% overestimate -> correction 0.92
    
    We use a smooth function for better interpolation.
    
    The correction REDUCES the underdog's 1UP probability to match market.
    """
    if ratio <= 1.0:
        return 1.0
    
    # Piecewise linear with smooth transitions
    # These values are derived from the analysis of fair_diff by lambda imbalance
    if ratio <= 1.2:
        # Balanced: slight correction
        return 1.0 - 0.03 * (ratio - 1.0) / 0.2
    elif ratio <= 1.8:
        # Moderate: increasing correction
        base = 0.97
        return base - 0.04 * (ratio - 1.2) / 0.6
    elif ratio <= 2.5:
        # High: peak correction
        base = 0.93
        return base - 0.03 * (ratio - 1.8) / 0.7
    else:
        # Extreme: slightly less correction (underdogs priced more accurately at extremes)
        return 0.90 + 0.02 * min((ratio - 2.5) / 1.5, 1.0)


def get_favorite_correction(ratio: float) -> float:
    """
    Get the probability correction factor for favorite based on lambda ratio.
    
    Favorites also need slight adjustment, but much smaller.
    Analysis shows favorites are about 3-4% overestimated consistently.
    """
    if ratio <= 1.0:
        return 1.0
    
    # Slight reduction for favorites
    base_correction = 0.97
    
    # The correction is relatively stable across ratios
    return base_correction


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
        def supremacy_loss(sup):
            l_home = (lambda_total + sup) / 2
            l_away = (lambda_total - sup) / 2
            # Apply empirical correction after supremacy adjustment
            l_home_corr, l_away_corr = empirical_underdog_correction(l_home, l_away)
            max_goals = 10
            home_win = 0.0
            draw = 0.0
            away_win = 0.0
            for h in range(max_goals+1):
                for a in range(max_goals+1):
                    p = (math.exp(-l_home_corr) * l_home_corr**h / math.factorial(h)) * (math.exp(-l_away_corr) * l_away_corr**a / math.factorial(a))
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
            lambda_home, lambda_away = empirical_underdog_correction(lambda_home, lambda_away)
        except Exception:
            # Fallback: coarse grid search over sup in [-2,2]
            sups = [x for x in np.linspace(-2.0, 2.0, 201)]
            best_sup = None
            best_loss = float('inf')
            for s in sups:
                l_home = (lambda_total + s) / 2
                l_away = (lambda_total - s) / 2
                l_home_corr, l_away_corr = empirical_underdog_correction(l_home, l_away)
                val = supremacy_loss(s)
                if val < best_loss:
                    best_loss = val
                    best_sup = s
            if best_sup is not None:
                supremacy = best_sup
                lambda_home = (lambda_total + supremacy) / 2
                lambda_away = (lambda_total - supremacy) / 2
                lambda_home, lambda_away = empirical_underdog_correction(lambda_home, lambda_away)

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
