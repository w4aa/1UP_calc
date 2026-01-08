"""
Handicap Calibrated Engine

Uses Asian Handicap markets to calibrate Poisson lambdas.

Asian Handicap line 0 (or -0.5/+0.5) gives:
- P(Home wins) ~ P(Home goals > Away goals)
- P(Away wins) ~ P(Away goals > Home goals)

Higher handicap lines provide additional constraints on
goal difference distributions.

Calibration approach:
1. Get base lambdas from O/U markets
2. Use handicap line (e.g., -0.5) to infer expected goal difference
3. Adjust lambdas to match the implied goal difference
"""

import math
from typing import Optional
from .base import (
    BaseEngine,
    devig_two_way,
    devig_three_way,
    infer_lambda_from_ou_market,
    simulate_1up_probabilities,
    poisson_cdf,
)


def estimate_goal_diff_from_handicap(lam_h: float, lam_a: float) -> float:
    """
    Estimate P(Home wins AH-0.5) = P(Home goals > Away goals).
    Uses Skellam distribution approximation via Monte Carlo.
    """
    # For Skellam: P(H > A) where H ~ Poisson(lam_h), A ~ Poisson(lam_a)
    # Approximate using difference of means and variance
    # Skellam mean = lam_h - lam_a, variance = lam_h + lam_a
    
    # Simple approximation: use normal approximation
    mean_diff = lam_h - lam_a
    var_diff = lam_h + lam_a
    
    if var_diff <= 0:
        return 0.5
    
    std_diff = math.sqrt(var_diff)
    
    # P(diff > 0) using normal approximation with continuity correction
    # P(X > 0) = P(Z > -mean/std)
    z = (0.5 - mean_diff) / std_diff  # continuity correction
    
    # Standard normal CDF approximation
    def norm_cdf(x):
        return 0.5 * (1 + math.erf(x / math.sqrt(2)))
    
    return 1.0 - norm_cdf(z)


class HandicapEngine(BaseEngine):
    """
    1UP engine calibrated using Asian Handicap market.
    """
    
    name = "Handicap"
    description = "Calibrates lambdas using Asian Handicap market"
    
    def calculate(self, markets: dict, bookmaker: str) -> Optional[dict]:
        """
        Calculate 1UP odds from market data.
        
        Args:
            markets: Dictionary with market data:
                - '1x2': (home, draw, away) odds
                - 'total_ou': (line, over, under) odds
                - 'home_ou': (line, over, under) odds
                - 'away_ou': (line, over, under) odds
                - 'asian_handicap': dict with {line: (home, away)} odds
            bookmaker: 'sporty' or 'pawa'
        
        Returns:
            Dictionary with calculation results or None if missing data
        """
        # Extract required markets
        x1x2 = markets.get('1x2')
        total_ou = markets.get('total_ou')
        home_ou = markets.get('home_ou')
        away_ou = markets.get('away_ou')
        asian_handicap = markets.get('asian_handicap')
        
        # Validate required data
        if not all([x1x2, total_ou, home_ou, away_ou]):
            return None
        
        home_1x2, draw_1x2, away_1x2 = x1x2
        total_line, total_over, total_under = total_ou
        home_line, home_over, home_under = home_ou
        away_line, away_over, away_under = away_ou
        
        if not all([home_1x2, draw_1x2, away_1x2]):
            return None
        if not all([total_line, total_over, total_under]):
            return None
        if not all([home_line, home_over, home_under]):
            return None
        if not all([away_line, away_over, away_under]):
            return None
        
        # Step 1: Get base lambdas from O/U markets
        lambda_home_raw = infer_lambda_from_ou_market(home_line, home_over, home_under)
        lambda_away_raw = infer_lambda_from_ou_market(away_line, away_over, away_under)
        lambda_total = infer_lambda_from_ou_market(total_line, total_over, total_under)
        
        # Scale to match total
        split_sum = lambda_home_raw + lambda_away_raw
        if split_sum > 0:
            factor = lambda_total / split_sum
            lambda_home_base = lambda_home_raw * factor
            lambda_away_base = lambda_away_raw * factor
        else:
            lambda_home_base = lambda_total * 0.5
            lambda_away_base = lambda_total * 0.5
        
        lambda_home = lambda_home_base
        lambda_away = lambda_away_base
        
        # Step 2: Apply Handicap calibration if available
        if asian_handicap and isinstance(asian_handicap, dict):
            # Prefer -0.5 line (home must win outright)
            best_line = None
            best_data = None
            
            for line in [-0.5, 0.5, -1.5, 1.5]:
                if line in asian_handicap:
                    best_line = line
                    best_data = asian_handicap[line]
                    break
            
            if best_line is not None and best_data and len(best_data) == 2:
                ah_home_odds, ah_away_odds = best_data
                
                if ah_home_odds and ah_away_odds:
                    # De-vig to get fair probability
                    p_ah_home = devig_two_way(ah_home_odds, ah_away_odds)
                    
                    # p_ah_home is P(Home goals > Away goals + line)
                    # For line = -0.5: P(Home goals > Away goals)
                    # For line = +0.5: P(Home goals >= Away goals)
                    
                    # Model prediction with current lambdas
                    model_p = estimate_goal_diff_from_handicap(lambda_home_base, lambda_away_base)
                    
                    # Calculate adjustment needed
                    # If market says higher P(home wins), increase home lambda relative to away
                    if model_p > 0.01 and model_p < 0.99:
                        # Ratio of market to model
                        ratio = p_ah_home / model_p
                        
                        # Apply modest adjustment (cap at 20%)
                        adj = min(max(ratio, 0.85), 1.15)
                        
                        # Adjust lambdas while preserving total
                        # Increase home and decrease away proportionally
                        mid = lambda_total / 2
                        diff_base = (lambda_home_base - lambda_away_base) / 2
                        
                        # Scale the difference
                        diff_new = diff_base * adj
                        
                        lambda_home = mid + diff_new
                        lambda_away = mid - diff_new
                        
                        # Ensure non-negative
                        if lambda_home < 0.1:
                            lambda_home = 0.1
                            lambda_away = lambda_total - 0.1
                        if lambda_away < 0.1:
                            lambda_away = 0.1
                            lambda_home = lambda_total - 0.1
        
        lambda_total_final = lambda_home + lambda_away
        
        # Step 3: Run Monte Carlo simulation
        p_home_1up, p_away_1up = simulate_1up_probabilities(
            lambda_home, lambda_away,
            n_sims=self.n_sims,
            match_minutes=self.match_minutes
        )
        
        # Build result
        return self._build_result(
            lambda_home=lambda_home,
            lambda_away=lambda_away,
            lambda_total=lambda_total_final,
            p_home_1up=p_home_1up,
            p_away_1up=p_away_1up,
            draw_odds=draw_1x2,
            input_1x2={
                'home': home_1x2,
                'draw': draw_1x2,
                'away': away_1x2,
            }
        )
