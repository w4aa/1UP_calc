"""
First Goal Calibrated Engine

Uses the "First Team to Score" market to calibrate Poisson lambdas.

The FTS market gives probabilities for:
- Home scores first
- No goal
- Away scores first

From these we can extract:
- P(Home scores first | at least one goal) 
- P(No goals) -> helps calibrate total goals

Calibration approach:
1. Get base lambdas from O/U markets
2. Use FTS to adjust the home/away split ratio
3. Use P(No goals) to validate total lambda
"""

import math
from typing import Optional
from .base import (
    BaseEngine,
    devig_three_way,
    infer_lambda_from_ou_market,
    simulate_1up_probabilities,
)


class FirstGoalEngine(BaseEngine):
    """
    1UP engine calibrated using First Team to Score market.
    """
    
    name = "FirstGoal"
    description = "Calibrates lambdas using First Team to Score market"
    
    def calculate(self, markets: dict, bookmaker: str) -> Optional[dict]:
        """
        Calculate 1UP odds from market data.
        
        Args:
            markets: Dictionary with market data:
                - '1x2': (home, draw, away) odds
                - 'total_ou': (line, over, under) odds
                - 'home_ou': (line, over, under) odds
                - 'away_ou': (line, over, under) odds
                - 'first_goal': (home, no_goal, away) odds
            bookmaker: 'sporty' or 'pawa'
        
        Returns:
            Dictionary with calculation results or None if missing data
        """
        # Extract required markets
        x1x2 = markets.get('1x2')
        total_ou = markets.get('total_ou')
        home_ou = markets.get('home_ou')
        away_ou = markets.get('away_ou')
        first_goal = markets.get('first_goal')
        
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
        
        # Step 2: Apply First Goal calibration if available
        if first_goal and all(first_goal):
            fg_home, fg_no_goal, fg_away = first_goal
            p_fg_home, p_fg_no_goal, p_fg_away = devig_three_way(fg_home, fg_no_goal, fg_away)
            
            # Market-implied ratio of home first vs away first (given a goal is scored)
            p_goal = 1.0 - p_fg_no_goal
            if p_goal > 0.01:
                market_home_ratio = p_fg_home / p_goal
                market_away_ratio = p_fg_away / p_goal
                
                # Poisson model: P(home first | goal) = LH / (LH + LA)
                # Use this to adjust the split
                model_sum = lambda_home_raw + lambda_away_raw
                if model_sum > 0:
                    # Create calibrated lambdas maintaining total
                    lambda_home_cal = lambda_total * market_home_ratio
                    lambda_away_cal = lambda_total * market_away_ratio
                    
                    # Blend: 70% calibrated, 30% O/U-based
                    blend = 0.7
                    split_sum = lambda_home_raw + lambda_away_raw
                    if split_sum > 0:
                        factor = lambda_total / split_sum
                        lambda_home_ou = lambda_home_raw * factor
                        lambda_away_ou = lambda_away_raw * factor
                        
                        lambda_home = blend * lambda_home_cal + (1 - blend) * lambda_home_ou
                        lambda_away = blend * lambda_away_cal + (1 - blend) * lambda_away_ou
                    else:
                        lambda_home = lambda_home_cal
                        lambda_away = lambda_away_cal
                else:
                    # Fallback to standard scaling
                    lambda_home = lambda_total * 0.5
                    lambda_away = lambda_total * 0.5
            else:
                # Very low goal probability, use standard approach
                split_sum = lambda_home_raw + lambda_away_raw
                factor = lambda_total / split_sum if split_sum > 0 else 1.0
                lambda_home = lambda_home_raw * factor
                lambda_away = lambda_away_raw * factor
        else:
            # No FTS market, fallback to standard scaling
            split_sum = lambda_home_raw + lambda_away_raw
            factor = lambda_total / split_sum if split_sum > 0 else 1.0
            lambda_home = lambda_home_raw * factor
            lambda_away = lambda_away_raw * factor
        
        # Ensure total is preserved
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
