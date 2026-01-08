"""
Poisson Engine

Original 1UP pricing engine using O/U markets to infer Poisson lambdas.

Inputs used:
- 1X2 market (for draw odds)
- Total O/U market (match total)
- Home Team O/U market
- Away Team O/U market

Calibration:
1. Infer team lambdas from Home/Away O/U markets
2. Rescale to match total O/U market
3. Run Monte Carlo simulation
"""

from typing import Optional
from .base import (
    BaseEngine,
    devig_three_way,
    infer_lambda_from_ou_market,
    simulate_1up_probabilities,
)


class PoissonEngine(BaseEngine):
    """
    1UP engine using Poisson model calibrated from O/U markets.
    """
    
    name = "Poisson"
    description = "Uses O/U markets to infer Poisson lambdas"
    
    def calculate(self, markets: dict, bookmaker: str) -> Optional[dict]:
        """
        Calculate 1UP odds from market data.
        
        Args:
            markets: Dictionary with market data:
                - '1x2': (home, draw, away) odds
                - 'total_ou': (line, over, under) odds
                - 'home_ou': (line, over, under) odds
                - 'away_ou': (line, over, under) odds
            bookmaker: 'sporty' or 'pawa'
        
        Returns:
            Dictionary with calculation results or None if missing data
        """
        # Extract and validate required markets using BaseEngine helper
        validated = self._extract_and_validate_ou_markets(markets)
        if not validated:
            return None

        # Unpack validated markets
        home_1x2, draw_1x2, away_1x2 = validated['x1x2']
        total_line, total_over, total_under = validated['total_ou']
        home_line, home_over, home_under = validated['home_ou']
        away_line, away_over, away_under = validated['away_ou']

        # Step 1: De-vig 1X2 for reference
        p_home_win, p_draw, p_away_win = devig_three_way(home_1x2, draw_1x2, away_1x2)
        
        # Step 2: Infer team lambdas from team total markets
        lambda_home_raw = infer_lambda_from_ou_market(home_line, home_over, home_under)
        lambda_away_raw = infer_lambda_from_ou_market(away_line, away_over, away_under)
        split_sum = lambda_home_raw + lambda_away_raw
        
        # Step 3: Get total expected goals from match O/U and rescale
        lambda_total = infer_lambda_from_ou_market(total_line, total_over, total_under)
        
        if split_sum > 0:
            factor = lambda_total / split_sum
        else:
            factor = 1.0
        
        lambda_home = lambda_home_raw * factor
        lambda_away = lambda_away_raw * factor
        
        # Step 4: Run Monte Carlo simulation for 1UP probabilities
        p_home_1up, p_away_1up = simulate_1up_probabilities(
            lambda_home, lambda_away,
            n_sims=self.n_sims,
            match_minutes=self.match_minutes
        )
        
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
            }
        )
