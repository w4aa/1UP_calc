"""
Supremacy-Calibrated Poisson Engine

This engine infers Poisson lambdas using:
- Home/Away O/U markets (for initial lambdas)
- Total O/U market (for total goals)
- 1X2 market (for supremacy adjustment)

Steps:
1. Infer raw lambdas from Home/Away O/U markets
2. Infer total expected goals from match O/U
3. Infer supremacy from 1X2 market (using optimization)
4. Adjust lambdas so their sum matches total goals and their difference matches supremacy
5. Run Monte Carlo simulation for 1UP probabilities
"""

from typing import Optional
from .base import (
    BaseEngine,
    devig_three_way,
    infer_lambda_from_ou_market,
    simulate_1up_probabilities,
)

import numpy as np
import math
try:
    from scipy.optimize import minimize_scalar
except Exception:
    minimize_scalar = None

class SupremacyPoissonEngine(BaseEngine):
    """
    1UP engine using Poisson model calibrated from O/U and 1X2 markets.
    """
    name = "SupremacyPoisson"
    description = "Uses O/U and 1X2 markets to infer Poisson lambdas with supremacy adjustment"

    def calculate(self, markets: dict, bookmaker: str) -> Optional[dict]:
        x1x2 = markets.get('1x2')
        total_ou = markets.get('total_ou')
        home_ou = markets.get('home_ou')
        away_ou = markets.get('away_ou')

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

        # Step 1: De-vig 1X2 for reference
        p_home_win, p_draw, p_away_win = devig_three_way(home_1x2, draw_1x2, away_1x2)

        # Step 2: Infer team lambdas from team total markets
        lambda_home_raw = infer_lambda_from_ou_market(home_line, home_over, home_under)
        lambda_away_raw = infer_lambda_from_ou_market(away_line, away_over, away_under)
        # Step 3: Get total expected goals from match O/U
        lambda_total = infer_lambda_from_ou_market(total_line, total_over, total_under)

        # Step 4: Infer supremacy from 1X2 market
        # Supremacy = lambda_home - lambda_away that best matches 1X2 probs under Poisson
        def loss(sup):
            # Adjust lambdas to match total and given supremacy
            l_home = (lambda_total + sup) / 2
            l_away = (lambda_total - sup) / 2
            # Compute Poisson 1X2 probabilities
            max_goals = 10
            home_win = 0.0
            draw = 0.0
            away_win = 0.0
            for h in range(max_goals+1):
                for a in range(max_goals+1):
                    p = (np.exp(-l_home) * l_home**h / math.factorial(h)) * (np.exp(-l_away) * l_away**a / math.factorial(a))
                    if h > a:
                        home_win += p
                    elif h == a:
                        draw += p
                    else:
                        away_win += p
            return (home_win - p_home_win)**2 + (draw - p_draw)**2 + (away_win - p_away_win)**2
        if minimize_scalar is not None:
            res = minimize_scalar(loss, bounds=(-2, 2), method='bounded')
            supremacy = res.x if res.success else lambda_home_raw - lambda_away_raw
        else:
            # Fallback: coarse grid search
            sups = np.linspace(-2.0, 2.0, 201)
            best_sup = sups[0]
            best_val = float('inf')
            for s in sups:
                val = loss(s)
                if val < best_val:
                    best_val = val
                    best_sup = s
            supremacy = best_sup

        # Step 5: Adjust lambdas to match total and supremacy
        lambda_home = (lambda_total + supremacy) / 2
        lambda_away = (lambda_total - supremacy) / 2

        # Step 6: Run Monte Carlo simulation for 1UP probabilities
        p_home_1up, p_away_1up = simulate_1up_probabilities(
            lambda_home, lambda_away,
            n_sims=self.n_sims,
            match_minutes=self.match_minutes
        )

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
                'supremacy': supremacy,
                'lambda_home_raw': lambda_home_raw,
                'lambda_away_raw': lambda_away_raw
            }
        )
