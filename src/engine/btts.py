"""
BTTS (Both Teams to Score) Calibrated Engine

Uses the GG/NG (BTTS Yes/No) market to calibrate Poisson lambdas.

BTTS market gives:
- P(Both teams score) = P(Home >= 1) * P(Away >= 1)
                      = (1 - e^-LH) * (1 - e^-LA)

This provides an additional constraint on the product of scoring probabilities.

Calibration approach:
1. Get base lambdas from O/U markets
2. Use BTTS probability to adjust lambdas
3. If BTTS prob is higher than model, increase both lambdas
4. If lower, decrease the weaker team's lambda
"""

import math
from typing import Optional
from .base import (
    BaseEngine,
    devig_two_way,
    devig_three_way,
    infer_lambda_from_ou_market,
    simulate_1up_probabilities,
)


def p_btts_from_lambdas(lam_h: float, lam_a: float) -> float:
    """
    Calculate P(Both teams score) from Poisson lambdas.
    P(BTTS) = P(H >= 1) * P(A >= 1) = (1 - e^-LH) * (1 - e^-LA)
    """
    p_home_scores = 1.0 - math.exp(-lam_h)
    p_away_scores = 1.0 - math.exp(-lam_a)
    return p_home_scores * p_away_scores


def infer_lambda_from_p_score(p_score: float) -> float:
    """
    Given P(team scores >= 1), infer lambda.
    P(X >= 1) = 1 - e^-L  =>  L = -ln(1 - P)
    """
    if p_score <= 0:
        return 0.01
    if p_score >= 1:
        return 5.0  # Cap at high value
    return -math.log(1.0 - p_score)


class BTTSEngine(BaseEngine):
    """
    1UP engine calibrated using BTTS (Both Teams to Score) market.
    """
    
    name = "BTTS"
    description = "Calibrates lambdas using GG/NG (BTTS) market"
    
    def calculate(self, markets: dict, bookmaker: str) -> Optional[dict]:
        """
        Calculate 1UP odds from market data.
        
        Args:
            markets: Dictionary with market data:
                - '1x2': (home, draw, away) odds
                - 'total_ou': (line, over, under) odds
                - 'home_ou': (line, over, under) odds
                - 'away_ou': (line, over, under) odds
                - 'btts': (yes_odds, no_odds)
            bookmaker: 'sporty' or 'pawa'
        
        Returns:
            Dictionary with calculation results or None if missing data
        """
        # Extract required markets
        x1x2 = markets.get('1x2')
        total_ou = markets.get('total_ou')
        home_ou = markets.get('home_ou')
        away_ou = markets.get('away_ou')
        btts = markets.get('btts')
        
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
        
        # Step 2: Apply BTTS calibration if available
        if btts and len(btts) == 2:
            btts_yes, btts_no = btts
            
            if btts_yes and btts_no:
                # De-vig to get fair P(BTTS)
                p_btts_market = devig_two_way(btts_yes, btts_no)
                
                # Model prediction
                p_btts_model = p_btts_from_lambdas(lambda_home_base, lambda_away_base)
                
                if p_btts_model > 0.01 and p_btts_model < 0.99:
                    # Calculate ratio
                    ratio = p_btts_market / p_btts_model
                    
                    # If market BTTS is higher, both teams are expected to score more
                    # If lower, less likely both score
                    
                    # Approach: adjust P(score) for each team, then convert back to lambda
                    p_home_scores_base = 1.0 - math.exp(-lambda_home_base)
                    p_away_scores_base = 1.0 - math.exp(-lambda_away_base)
                    
                    # Take sqrt of ratio to distribute adjustment between both teams
                    adj_factor = math.sqrt(ratio)
                    
                    # Cap adjustment at 15%
                    adj_factor = min(max(adj_factor, 0.87), 1.15)
                    
                    # Apply adjustment
                    p_home_scores_adj = min(p_home_scores_base * adj_factor, 0.99)
                    p_away_scores_adj = min(p_away_scores_base * adj_factor, 0.99)
                    
                    # Convert back to lambdas
                    lambda_home_btts = infer_lambda_from_p_score(p_home_scores_adj)
                    lambda_away_btts = infer_lambda_from_p_score(p_away_scores_adj)
                    
                    # Rescale to preserve total (or close to it)
                    btts_sum = lambda_home_btts + lambda_away_btts
                    if btts_sum > 0:
                        # Blend towards target total
                        scale = lambda_total / btts_sum
                        # Don't over-correct: use partial scaling
                        scale = 0.5 + 0.5 * scale  # Move halfway to target
                        
                        lambda_home = lambda_home_btts * scale
                        lambda_away = lambda_away_btts * scale
        
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
