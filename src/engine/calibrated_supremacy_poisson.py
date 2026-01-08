"""
Calibrated Supremacy Poisson Engine

Combines empirical calibration (underdog correction) from CalibratedPoissonEngine
with supremacy adjustment from SupremacyPoissonEngine.
"""

from typing import Optional
from .base import (
    BaseEngine,
    devig_three_way,
    infer_lambda_from_ou_market,
    simulate_1up_probabilities,
)
from .poisson_calibrated import empirical_underdog_correction
import numpy as np
try:
    from scipy.optimize import minimize_scalar
except Exception:
    minimize_scalar = None
import math

class CalibratedSupremacyPoissonEngine(BaseEngine):
    name = "CalibratedSupremacyPoisson"
    description = "Empirical underdog correction + supremacy adjustment (O/U + 1X2)"

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

        # Step 4: Apply empirical underdog correction (as in CalibratedPoissonEngine)
        lambda_home_corr, lambda_away_corr = empirical_underdog_correction(lambda_home_raw, lambda_away_raw)

        # Step 5: Supremacy optimization (as in SupremacyPoissonEngine)
        def loss(sup):
            l_home = (lambda_total + sup) / 2
            l_away = (lambda_total - sup) / 2
            # Empirical correction after supremacy adjustment
            l_home_corr, l_away_corr = empirical_underdog_correction(l_home, l_away)
            max_goals = 10
            home_win = 0.0
            draw = 0.0
            away_win = 0.0
            for h in range(max_goals+1):
                for a in range(max_goals+1):
                    p = (np.exp(-l_home_corr) * l_home_corr**h / math.factorial(h)) * (np.exp(-l_away_corr) * l_away_corr**a / math.factorial(a))
                    if h > a:
                        home_win += p
                    elif h == a:
                        draw += p
                    else:
                        away_win += p
            return (home_win - p_home_win)**2 + (draw - p_draw)**2 + (away_win - p_away_win)**2
        if minimize_scalar is not None:
            res = minimize_scalar(loss, bounds=(-2, 2), method='bounded')
            supremacy = res.x if res.success else (lambda_home_corr - lambda_away_corr)
        else:
            sups = np.linspace(-2.0, 2.0, 201)
            best_sup = sups[0]
            best_val = float('inf')
            for s in sups:
                val = loss(s)
                if val < best_val:
                    best_val = val
                    best_sup = s
            supremacy = best_sup

        # Step 6: Final lambdas after both corrections
        lambda_home_final = (lambda_total + supremacy) / 2
        lambda_away_final = (lambda_total - supremacy) / 2
        lambda_home_final, lambda_away_final = empirical_underdog_correction(lambda_home_final, lambda_away_final)

        # Step 7: Monte Carlo simulation for 1UP probabilities
        p_home_1up, p_away_1up = simulate_1up_probabilities(
            lambda_home_final, lambda_away_final,
            n_sims=self.n_sims,
            match_minutes=self.match_minutes
        )

        # draw_odds and input_1x2 are not used in this engine, pass None or empty dict
        extra = {
            'engine': self.name,
            '1up_home_fair': 1.0 / p_home_1up if p_home_1up else None,
            '1up_away_fair': 1.0 / p_away_1up if p_away_1up else None,
            '1up_draw': None
        }
        return self._build_result(
            lambda_home_final,
            lambda_away_final,
            lambda_home_final + lambda_away_final,
            p_home_1up,
            p_away_1up,
            None,  # draw_odds
            {},    # input_1x2
            extra
        )
