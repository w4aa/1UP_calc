"""
FTS-Calibrated DP Engine

This engine uses First Team To Score (FTS) odds to anchor early scoring dynamics
while maintaining total expected goals from 1X2 + O/U markets.

Key features:
1. FTS-anchored: Uses FTS market to override scoring share
2. DP-based: No Monte Carlo, deterministic dynamic programming
3. Post-FTS calibrated: Applies global 2-parameter calibration to match Sporty + Bet9ja
4. Provider-aware: Explicitly uses Sporty FTS for Betpawa (same odds provider)

Calibration constants (fitted to Sporty + Bet9ja actual 1UP odds):
    a = 0.17721692133648134
    b = 1.1581541486316087
    logit(p_adj) = a + b * logit(p_model)
"""

import math
import numpy as np
from typing import Optional, Tuple, Dict
from .base import (
    BaseEngine,
    devig_two_way,
    devig_three_way,
    fit_lambda_from_ou_lines,
)

# Global calibration constants (fitted to Sporty + Bet9ja)
CALIBRATION_A = 0.17721692133648134
CALIBRATION_B = 1.1581541486316087


def logit(p: float) -> float:
    """Convert probability to logit scale, with bounds protection."""
    p = max(1e-9, min(1 - 1e-9, p))
    return math.log(p / (1 - p))


def inv_logit(x: float) -> float:
    """Convert logit back to probability, with bounds protection."""
    x = max(-20, min(20, x))  # Prevent overflow
    return 1.0 / (1.0 + math.exp(-x))


def apply_calibration(p: float) -> float:
    """
    Apply post-FTS calibration using fitted constants.

    logit(p_adj) = a + b * logit(p_model)
    """
    if p <= 1e-6 or p >= 1 - 1e-6:
        return max(1e-6, min(1 - 1e-6, p))

    logit_p = logit(p)
    logit_adj = CALIBRATION_A + CALIBRATION_B * logit_p
    p_adj = inv_logit(logit_adj)

    return max(1e-6, min(1 - 1e-6, p_adj))


class FTSCalibratedDPEngine(BaseEngine):
    """
    FTS-Calibrated DP Engine for 1UP odds calculation.

    Uses dynamic programming to compute hit probabilities based on:
    - Total expected goals from O/U 2.5
    - Scoring share overridden by First Team To Score odds
    - Post-FTS calibration to match market prices

    IMPORTANT: For Betpawa, uses Sporty FTS (same odds provider).
    """

    name = "FTS-Calibrated-DP"
    description = "FTS-anchored DP with post-FTS calibration (provider-aware)"

    def __init__(self, n_sims: int = 30000, match_minutes: int = 95, margin_pct: float = 0.05):
        super().__init__(n_sims, match_minutes, margin_pct)
        self.max_goals = 15  # DP upper bound for total goals

    def calculate(self, markets: dict, bookmaker: str) -> Optional[dict]:
        """
        Calculate 1UP odds using FTS-calibrated DP method.

        Args:
            markets: Dict with market odds from _prepare_market_data
            bookmaker: 'sporty', 'pawa', or 'bet9ja'

        Returns:
            Dict with calculated results, or None if data insufficient
        """

        # STEP A: Extract required markets
        x1x2 = markets.get('1x2')
        total_ou = markets.get('total_ou')
        first_goal = markets.get('first_goal')
        btts = markets.get('btts')

        # Validate 1X2
        if not x1x2 or not all(x1x2):
            return None

        home_1x2, draw_1x2, away_1x2 = x1x2

        # STEP B: Fit base scoring share from 1X2 (needed for BTTS fallback)
        p_home_win, p_draw, p_away_win = devig_three_way(home_1x2, draw_1x2, away_1x2)

        # Rough p_share estimate for BTTS fallback (refined later with FTS)
        # Use supremacy approximation
        p_share_estimate = 0.5 + 0.1 * (p_home_win - p_away_win)
        p_share_estimate = max(0.1, min(0.9, p_share_estimate))

        # STEP C: Fit lambda_total from O/U 2.5 (BTTS fallback with p_share)
        lambda_total = self._fit_lambda_total(total_ou, btts, p_share_estimate)
        if lambda_total is None:
            return None

        # STEP D: Fit precise base lambdas from 1X2
        lambda_home_base, lambda_away_base = self._fit_lambda_from_1x2(
            p_home_win, p_draw, p_away_win, lambda_total
        )
        p_base = lambda_home_base / lambda_total if lambda_total > 0 else 0.5

        # STEP D: Determine FTS source (CRITICAL - Provider-aware)
        fts_source, fts_odds = self._get_fts_odds(first_goal, bookmaker)

        if fts_odds is None:
            # No FTS available - fall back to base share
            lambda_home = lambda_home_base
            lambda_away = lambda_away_base
            p_cond = p_base
            p_nog = None
            fts_source = "none_fallback_to_1x2"
        else:
            # STEP E: Override scoring share using FTS
            fg_home, fg_nog, fg_away = fts_odds
            p_cond, p_nog = self._compute_conditional_share_from_fts(
                fg_home, fg_nog, fg_away
            )

            # Clamp p_cond
            p_cond = max(1e-6, min(1 - 1e-6, p_cond))

            lambda_home = lambda_total * p_cond
            lambda_away = lambda_total * (1 - p_cond)

        # STEP F: DP-based hit probabilities (NO Monte Carlo)
        p_home_1up_raw, p_away_1up_raw, p_draw_ft = self._compute_hit_probs_dp(
            lambda_total, p_cond
        )

        # STEP G: Post-FTS calibration (CRITICAL)
        p_home_1up = apply_calibration(p_home_1up_raw)
        p_away_1up = apply_calibration(p_away_1up_raw)

        # STEP H: Convert to odds
        fair_home = 1.0 / p_home_1up
        fair_away = 1.0 / p_away_1up
        fair_draw = draw_1x2  # Use bookmaker's draw odds

        # Build result with debug info
        return self._build_result(
            lambda_home=lambda_home,
            lambda_away=lambda_away,
            lambda_total=lambda_total,
            p_home_1up=p_home_1up,
            p_away_1up=p_away_1up,
            draw_odds=fair_draw,
            input_1x2={'home': home_1x2, 'draw': draw_1x2, 'away': away_1x2},
            extra={
                # Debug fields
                'fts_source': fts_source,
                'p_cond_from_fts': p_cond,
                'p_nog': p_nog,
                'p_home_1up_raw': p_home_1up_raw,
                'p_away_1up_raw': p_away_1up_raw,
                'p_home_win': p_home_win,
                'p_draw': p_draw,
                'p_away_win': p_away_win,
                'p_draw_ft': p_draw_ft,
                'lambda_home_base': lambda_home_base,
                'lambda_away_base': lambda_away_base,
                'p_base': p_base,
            }
        )

    def _fit_lambda_total(self, total_ou: tuple, btts: tuple, p_share: float = 0.5) -> Optional[float]:
        """
        Fit lambda_total from O/U 2.5 (BTTS fallback with proper solver).

        Args:
            total_ou: Over/Under odds tuple
            btts: BTTS odds tuple
            p_share: Scoring share for BTTS fallback (from FTS or 1X2)

        Returns:
            lambda_total or None if no data
        """
        # Try O/U 2.5 first
        if total_ou and len(total_ou) == 3:
            line, over_odds, under_odds = total_ou
            if line and over_odds and under_odds:
                # Handle list format (multiple lines)
                if isinstance(total_ou, list):
                    return fit_lambda_from_ou_lines(total_ou)
                else:
                    return fit_lambda_from_ou_lines([total_ou])

        # Fallback to BTTS with proper solver
        if btts and len(btts) == 2:
            btts_yes, btts_no = btts
            if btts_yes and btts_no:
                p_btts = devig_two_way(btts_yes, btts_no)

                # Solve for lambda_total using 1D search
                # Model: P(BTTS) = 1 - exp(-lh) - exp(-la) + exp(-(lh+la))
                # where lh = lambda_total * p_share, la = lambda_total * (1-p_share)

                best_lambda = 2.5
                best_error = float('inf')

                for lam_total in np.linspace(0.5, 5.5, 100):
                    lh = lam_total * p_share
                    la = lam_total * (1 - p_share)

                    # P(both score) = 1 - P(home 0) - P(away 0) + P(both 0)
                    model_btts = 1.0 - math.exp(-lh) - math.exp(-la) + math.exp(-(lh + la))

                    error = (model_btts - p_btts) ** 2

                    if error < best_error:
                        best_error = error
                        best_lambda = lam_total

                return best_lambda

        return None

    def _fit_lambda_from_1x2(
        self,
        p_home: float,
        p_draw: float,
        p_away: float,
        lambda_total: float
    ) -> Tuple[float, float]:
        """
        Fit lambda_home and lambda_away from 1X2 probabilities.

        Uses grid search to find lambdas that match 1X2 probs
        while respecting lambda_total constraint.
        """
        best_error = float('inf')
        best_lh = lambda_total * 0.5
        best_la = lambda_total * 0.5

        # Grid search over scoring share
        for p_share in np.linspace(0.1, 0.9, 81):
            lh = lambda_total * p_share
            la = lambda_total * (1 - p_share)

            # Compute match outcome probs using Poisson
            ph, pd, pa = self._poisson_match_probs(lh, la)

            # Error
            error = (ph - p_home)**2 + (pd - p_draw)**2 + (pa - p_away)**2

            if error < best_error:
                best_error = error
                best_lh = lh
                best_la = la

        return best_lh, best_la

    def _poisson_match_probs(self, lh: float, la: float) -> Tuple[float, float, float]:
        """Compute match outcome probabilities using Poisson."""
        max_g = 10
        ph_win = 0.0
        pd_draw = 0.0
        pa_win = 0.0

        for h in range(max_g + 1):
            for a in range(max_g + 1):
                p = (math.exp(-lh) * lh**h / math.factorial(h)) * \
                    (math.exp(-la) * la**a / math.factorial(a))

                if h > a:
                    ph_win += p
                elif h == a:
                    pd_draw += p
                else:
                    pa_win += p

        total = ph_win + pd_draw + pa_win
        if total > 0:
            return ph_win / total, pd_draw / total, pa_win / total
        return 0.33, 0.34, 0.33

    def _get_fts_odds(
        self,
        first_goal: dict,
        bookmaker: str
    ) -> Tuple[str, Optional[Tuple[float, float, float]]]:
        """
        Get FTS odds based on bookmaker and provider rules.

        CRITICAL LOGIC:
        - sporty → use sporty FTS
        - bet9ja → use bet9ja FTS
        - pawa → use sporty FTS (explicit provider sharing)

        Returns:
            (fts_source_label, (fg_home, fg_nog, fg_away) or None)
        """
        if not first_goal:
            return ("no_fts_data", None)

        # Determine which provider's FTS to use
        if bookmaker == "pawa":
            # Betpawa uses Sporty FTS (same provider)
            fts_provider = "sporty"
            source_label = "sporty_for_pawa"
        elif bookmaker == "sporty":
            fts_provider = "sporty"
            source_label = "sporty"
        elif bookmaker == "bet9ja":
            fts_provider = "bet9ja"
            source_label = "bet9ja"
        else:
            return ("unknown_bookmaker", None)

        # Extract FTS odds from the determined provider
        # first_goal is dict with 'sporty' and 'bet9ja' keys
        # Each contains (fg_home, fg_nog, fg_away) or None values
        if isinstance(first_goal, dict):
            fts_data = first_goal.get(fts_provider)
            if fts_data and len(fts_data) == 3:
                fg_home, fg_nog, fg_away = fts_data
                if fg_home and fg_nog and fg_away:
                    return (source_label, (fg_home, fg_nog, fg_away))

        # If standard extraction failed, try direct tuple format
        # (for backward compatibility with existing runner format)
        if isinstance(first_goal, tuple) and len(first_goal) == 3:
            fg_home, fg_nog, fg_away = first_goal
            if fg_home and fg_nog and fg_away:
                # Assume it's from the current bookmaker context
                return (f"{bookmaker}_direct", first_goal)

        return (f"no_{fts_provider}_fts", None)

    def _compute_conditional_share_from_fts(
        self,
        fg_home: float,
        fg_nog: float,
        fg_away: float
    ) -> Tuple[float, float]:
        """
        Compute conditional scoring share from FTS odds.

        Returns:
            (p_cond, p_nog)
            p_cond = P(Home scores first | someone scores)
            p_nog = P(No goal in match)
        """
        # Convert odds to implied probs
        q_home = 1.0 / fg_home
        q_nog = 1.0 / fg_nog
        q_away = 1.0 / fg_away

        # Normalize
        total = q_home + q_nog + q_away
        p_home = q_home / total
        p_nog = q_nog / total
        p_away = q_away / total

        # Conditional share (given someone scores)
        if (1 - p_nog) > 1e-9:
            p_cond = p_home / (1 - p_nog)
        else:
            p_cond = 0.5

        return p_cond, p_nog

    def _compute_hit_probs_dp(
        self,
        lambda_total: float,
        p_cond: float
    ) -> Tuple[float, float, float]:
        """
        Compute hit probabilities using correct absorbing-barrier DP.

        Model:
        - Total goals N ~ Poisson(lambda_total)
        - Each goal is Home with prob p_cond, Away with prob (1 - p_cond)
        - For fixed N, compute P(ever hit barrier ±1) using absorbing DP

        This correctly handles paths that hit ±1 then revert (common in football).

        Returns:
            (p_home_1up, p_away_1up, p_draw_ft)
        """
        max_goals = self.max_goals

        p_home_1up_total = 0.0
        p_away_1up_total = 0.0
        p_draw_ft_total = 0.0

        # For each possible total goal count
        for n in range(max_goals + 1):
            # Poisson probability of exactly n goals
            if n == 0:
                p_n = math.exp(-lambda_total)
            else:
                p_n = math.exp(-lambda_total) * (lambda_total ** n) / math.factorial(n)

            if p_n < 1e-15:
                continue

            # Compute hit probabilities for this n using absorbing DP
            ph1 = self._prob_hit_barrier(n, p_cond, barrier=+1)
            pa1 = self._prob_hit_barrier(n, p_cond, barrier=-1)

            # Draw probability: P(#home = #away) = P(#home = n/2)
            if n % 2 == 0:
                k = n // 2
                pd = math.comb(n, k) * (p_cond ** k) * ((1 - p_cond) ** k)
            else:
                pd = 0.0

            # Accumulate weighted by Poisson
            p_home_1up_total += p_n * ph1
            p_away_1up_total += p_n * pa1
            p_draw_ft_total += p_n * pd

        # Clamp for numerical stability
        p_home_1up_total = max(1e-9, min(1 - 1e-9, p_home_1up_total))
        p_away_1up_total = max(1e-9, min(1 - 1e-9, p_away_1up_total))
        p_draw_ft_total = max(1e-9, min(1 - 1e-9, p_draw_ft_total))

        return p_home_1up_total, p_away_1up_total, p_draw_ft_total

    def _prob_hit_barrier(self, n: int, p: float, barrier: int) -> float:
        """
        Compute P(ever hit barrier during n-step random walk) using absorbing DP.

        For barrier = +1:
        - Start at diff = 0
        - Allowed states are [-n, ..., 0] (below barrier)
        - Each step: +1 with prob p (home goal), -1 with prob (1-p) (away goal)
        - Absorb when reaching +1
        - Return total absorbed mass after n steps

        For barrier = -1: symmetric (or equivalently swap p and 1-p and barrier sign)

        Args:
            n: Number of goals
            p: Probability of home goal
            barrier: +1 or -1

        Returns:
            Probability of hitting barrier at any point during n steps
        """
        if n == 0:
            return 0.0

        if barrier == +1:
            # Allowed diffs: [-n, ..., 0]
            # Absorbing at +1
            # DP: mass[d] = probability mass at diff d without having hit +1

            # State indexing: diff in [-n, 0] → index [0, n]
            # mass[i] corresponds to diff = -n + i
            size = n + 1
            mass = np.zeros(size)
            mass[n] = 1.0  # Start at diff=0 (index n corresponds to diff=0)

            absorbed = 0.0

            for step in range(n):
                new_mass = np.zeros(size)

                for i in range(size):
                    if mass[i] < 1e-15:
                        continue

                    current_diff = -n + i

                    # Home goal: diff +1
                    new_diff = current_diff + 1
                    if new_diff == +1:
                        # Hit barrier, absorb
                        absorbed += mass[i] * p
                    elif -n <= new_diff <= 0:
                        # Still in allowed range
                        new_idx = new_diff + n
                        new_mass[new_idx] += mass[i] * p

                    # Away goal: diff -1
                    new_diff = current_diff - 1
                    if new_diff >= -n:
                        # Still in allowed range (can't hit +1 by going down)
                        new_idx = new_diff + n
                        new_mass[new_idx] += mass[i] * (1 - p)

                mass = new_mass

            return absorbed

        elif barrier == -1:
            # Symmetric: swap p → (1-p) and use +1 logic
            return self._prob_hit_barrier(n, 1 - p, +1)

        else:
            return 0.0

    def _compute_hit_probs_for_n_goals(
        self,
        n_goals: int,
        p_home: float
    ) -> Tuple[float, float, float]:
        """
        For exactly n goals, compute P(hit +1), P(hit -1), P(draw).

        This uses exact combinatorial calculation.
        """
        if n_goals == 0:
            return 0.0, 0.0, 1.0

        # State: (score_diff, hit_plus1, hit_minus1)
        # We track whether we've ever hit +1 or -1
        # Use memoization
        from functools import lru_cache

        @lru_cache(maxsize=10000)
        def dp(goals_left: int, diff: int, hit_p1: bool, hit_m1: bool) -> float:
            """
            Probability of reaching this state.

            Args:
                goals_left: Goals remaining to assign
                diff: Current score difference (home - away)
                hit_p1: Have we hit +1?
                hit_m1: Have we hit -1?

            Returns:
                Probability of this path
            """
            if goals_left == 0:
                return 1.0

            prob = 0.0

            # Next goal is home
            new_diff = diff + 1
            new_hit_p1 = hit_p1 or (new_diff == 1)
            prob += p_home * dp(goals_left - 1, new_diff, new_hit_p1, hit_m1)

            # Next goal is away
            new_diff = diff - 1
            new_hit_m1 = hit_m1 or (new_diff == -1)
            prob += (1 - p_home) * dp(goals_left - 1, new_diff, hit_p1, new_hit_m1)

            return prob

        # Start from 0-0
        total_prob = 1.0

        # Enumerate final states
        p_hit_p1 = 0.0
        p_hit_m1 = 0.0
        p_draw = 0.0

        # We need to enumerate all possible outcomes
        # This is exponential but cached
        # Better approach: iterate over all possible score combinations

        for h in range(n_goals + 1):
            a = n_goals - h
            final_diff = h - a

            # Probability of this exact score
            p_score = (math.comb(n_goals, h) *
                      (p_home ** h) *
                      ((1 - p_home) ** a))

            # Check if this score path hit +1 or -1
            # We need to check all paths to (h, a)
            # This is complex - use simulation or exact DP

            # Simplified: check if path could have hit +1 or -1
            # A path to (h, a) hits +1 if at some point diff = +1
            # This happens if h >= a + 1

            # Use Ballot theorem or path counting
            # P(ever hit +1 | end at (h,a)) uses reflection principle

            hit_p1_this_score = self._prob_hit_value(h, a, 1)
            hit_m1_this_score = self._prob_hit_value(h, a, -1)

            p_hit_p1 += p_score * hit_p1_this_score
            p_hit_m1 += p_score * hit_m1_this_score

            if final_diff == 0:
                p_draw += p_score

        return p_hit_p1, p_hit_m1, p_draw

    def _prob_hit_value(self, h: int, a: int, target: int) -> float:
        """
        Probability that a random walk hits target value given final state (h, a).

        Uses reflection principle.
        """
        final_diff = h - a

        if target == 1:
            # Did we hit +1 on path to (h, a)?
            if final_diff >= 1:
                # Must have passed through +1
                return 1.0
            else:
                # Path ends below +1
                # Check if we ever touched +1
                # Use ballot/reflection theorem
                # If final_diff < 1, we need at least one moment where diff = 1
                # This requires h >= a + 1 at some point
                # Which means max_diff >= 1

                # For path ending at (h, a) with h < a+1:
                # Never hit +1
                return 0.0

        elif target == -1:
            # Did we hit -1 on path to (h, a)?
            if final_diff <= -1:
                return 1.0
            else:
                return 0.0

        return 0.0
