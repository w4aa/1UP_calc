try:
    from scipy.optimize import minimize
except Exception:
    minimize = None

# ===== Multi-line O/U Lambda Fitting (Base Level) =====
def fit_lambda_from_ou_lines(lines_odds: list) -> float:
    """
    Fit Poisson lambda to all available O/U lines and odds.
    Args:
        lines_odds: List of tuples (line, odds_over, odds_under)
    Returns:
        Fitted Poisson lambda
    """
    def is_valid(t):
        line, odds_over, odds_under = t
        return (
            line is not None and odds_over is not None and odds_under is not None
            and isinstance(odds_over, (float, int)) and isinstance(odds_under, (float, int))
            and odds_over > 1.01 and odds_under > 1.01
        )
    filtered = [t for t in lines_odds if is_valid(t)]
    if not filtered:
        return 1.8  # fallback default
    def loss(lam):
        lam_scalar = float(lam) if isinstance(lam, (float, int)) else float(lam[0])
        err = 0.0
        for line, odds_over, odds_under in filtered:
            p_over = devig_two_way(odds_over, odds_under)
            p_model = effective_over_prob(lam_scalar, line)
            err += (p_model - p_over) ** 2
        return err
    if minimize is not None:
        res = minimize(loss, x0=[1.8], bounds=[(0.01, 8.0)], method='L-BFGS-B')
        return float(res.x[0]) if res.success else 1.8
    # Fallback: simple grid search if scipy not available
    grid = np.linspace(0.01, 8.0, 400)
    losses = [loss(g) for g in grid]
    best = grid[int(np.argmin(losses))]
    return float(best)
"""
Base Engine Module

Contains shared utility functions for all 1UP engines:
- De-vigging functions
- Poisson sampling
- Monte Carlo simulation core (NumPy vectorized for speed)
"""

import math
import random
from typing import Tuple

import numpy as np


# ========== De-vigging Functions ==========

def devig_two_way(odds_yes: float, odds_no: float) -> float:
    """
    De-vig a 2-way market to get fair probability for 'Yes'.
    
    Args:
        odds_yes: Decimal odds for Yes outcome
        odds_no: Decimal odds for No outcome
    
    Returns:
        De-vigged probability of Yes outcome (0.0 to 1.0)
    """
    q_yes = 1.0 / odds_yes
    q_no = 1.0 / odds_no
    total = q_yes + q_no
    return q_yes / total


def devig_three_way(o1: float, o2: float, o3: float) -> Tuple[float, float, float]:
    """
    De-vig a 3-way market to get fair probabilities.
    
    Args:
        o1, o2, o3: Decimal odds for each outcome
    
    Returns:
        Tuple of (p1, p2, p3) - de-vigged probabilities
    """
    q1 = 1.0 / o1
    q2 = 1.0 / o2
    q3 = 1.0 / o3
    total = q1 + q2 + q3
    return q1 / total, q2 / total, q3 / total


# ========== Poisson Functions ==========

def poisson_cdf(k: int, lam: float) -> float:
    """
    Poisson CDF: P(N <= k) with mean lam.
    """
    if k < 0:
        return 0.0
    term = math.exp(-lam)
    s = term
    for i in range(1, k + 1):
        term *= lam / i
        s += term
    return s


def poisson_tail(threshold: int, lam: float) -> float:
    """
    Poisson tail probability: P(N >= threshold).
    """
    if threshold <= 0:
        return 1.0
    return 1.0 - poisson_cdf(threshold - 1, lam)


def effective_over_prob(lam: float, line: float) -> float:
    """
    Approximate P(Goals > line) for a total line.
    Handles quarter lines by rounding to nearest 0.5.
    """
    adj_line = round(line * 2.0) / 2.0
    threshold = math.floor(adj_line) + 1
    return poisson_tail(threshold, lam)


def poisson_sample(lam: float) -> int:
    """
    Sample from Poisson distribution using Knuth's algorithm.
    """
    if lam <= 0:
        return 0
    L = math.exp(-lam)
    k = 0
    p = 1.0
    while p > L:
        k += 1
        p *= random.random()
    return k - 1


# ========== Lambda Inference ==========

def infer_lambda_from_ou_market(line: float, odds_over: float, odds_under: float) -> float:
    """
    Infer Poisson lambda from an Over/Under market using binary search.
    
    Args:
        line: Goals line (e.g. 2.5)
        odds_over: Decimal odds for Over
        odds_under: Decimal odds for Under
    
    Returns:
        Poisson mean (lambda) consistent with the market
    """
    p_over = devig_two_way(odds_over, odds_under)
    
    # Binary search for lambda
    lam_low = 0.01
    lam_high = 6.0
    
    # Expand upper bound if needed
    for _ in range(20):
        if effective_over_prob(lam_high, line) >= p_over:
            break
        lam_high *= 2.0
    
    # Binary search
    for _ in range(50):
        lam_mid = 0.5 * (lam_low + lam_high)
        p_mid = effective_over_prob(lam_mid, line)
        if p_mid < p_over:
            lam_low = lam_mid
        else:
            lam_high = lam_mid
    
    return 0.5 * (lam_low + lam_high)


# ========== Monte Carlo Simulation ==========

def simulate_1up_probabilities(
    lambda_home: float, 
    lambda_away: float, 
    n_sims: int = 50000,
    match_minutes: int = 95
) -> Tuple[float, float]:
    """
    Monte Carlo simulation for 1UP payout probabilities.
    
    Uses NumPy vectorization for ~50x faster execution.
    
    Simulates matches by:
      1. Sampling goal counts from Poisson distributions
      2. Assigning random times to each goal
      3. Tracking if either team ever leads by >=1 goal
    
    Args:
        lambda_home: Expected goals for home team
        lambda_away: Expected goals for away team
        n_sims: Number of simulations
        match_minutes: Match duration (e.g. 95 for 90+5)
    
    Returns:
        Tuple of (p_home_1up, p_away_1up):
          p_home_1up: Probability Home 1UP bet pays
          p_away_1up: Probability Away 1UP bet pays
    """
    return _simulate_1up_vectorized(lambda_home, lambda_away, n_sims, match_minutes)


def _simulate_1up_vectorized(
    lambda_home: float, 
    lambda_away: float, 
    n_sims: int,
    match_minutes: int
) -> Tuple[float, float]:
    """
    Fully NumPy-vectorized 1UP simulation - NO Python loops.
    
    Key insight: Instead of simulating exact goal times and checking leads,
    we use a mathematical approach:
    - Home leads at some point if they score the first goal, OR
    - They take the lead at any point during the match
    
    For accurate simulation with variable goal counts, we use a fixed-size
    approach with masked arrays.
    """
    # Sample goal counts for all simulations at once
    home_goals = np.random.poisson(lambda_home, n_sims)
    away_goals = np.random.poisson(lambda_away, n_sims)
    total_goals = home_goals + away_goals
    
    # Handle zero-goal games
    no_goals_mask = total_goals == 0
    if np.all(no_goals_mask):
        return 0.0, 0.0
    
    # Maximum goals we need to handle (cap for memory efficiency)
    max_goals = min(int(total_goals.max()), 20)  # Cap at 20 goals per game
    
    if max_goals == 0:
        return 0.0, 0.0
    
    # Create arrays for goal times: shape (n_sims, max_goals)
    # Generate all random times at once
    all_times = np.random.uniform(0, match_minutes, (n_sims, max_goals))
    
    # Create team assignment arrays: +1 for home, -1 for away
    # For each sim, first home_goals[i] slots are home, next away_goals[i] are away
    goal_indices = np.arange(max_goals)  # [0, 1, 2, ..., max_goals-1]
    
    # Broadcast: (n_sims, 1) vs (max_goals,) -> (n_sims, max_goals)
    home_mask = goal_indices < home_goals[:, np.newaxis]  # True where goal is home
    away_mask = (goal_indices >= home_goals[:, np.newaxis]) & (goal_indices < total_goals[:, np.newaxis])
    valid_mask = goal_indices < total_goals[:, np.newaxis]  # True where goal exists
    
    # Team values: +1 for home, -1 for away, 0 for no goal
    teams = np.zeros((n_sims, max_goals), dtype=np.float32)
    teams[home_mask] = 1.0
    teams[away_mask] = -1.0
    
    # Sort goals by time within each simulation
    # Replace invalid times with infinity so they sort to the end
    sort_times = np.where(valid_mask, all_times, np.inf)
    sort_order = np.argsort(sort_times, axis=1)
    
    # Gather teams in sorted order
    row_indices = np.arange(n_sims)[:, np.newaxis]
    teams_sorted = teams[row_indices, sort_order]
    
    # Compute cumulative score difference for each simulation
    # Shape: (n_sims, max_goals)
    cumsum_diff = np.cumsum(teams_sorted, axis=1)
    
    # Mask out invalid positions (where there was no goal)
    valid_sorted = valid_mask[row_indices, sort_order]
    cumsum_diff = np.where(valid_sorted, cumsum_diff, 0)
    
    # Check if home/away ever led in each simulation
    # Home leads when cumsum > 0, Away leads when cumsum < 0
    home_ever_led = np.any(cumsum_diff > 0, axis=1)  # Shape: (n_sims,)
    away_ever_led = np.any(cumsum_diff < 0, axis=1)  # Shape: (n_sims,)
    
    # Count wins (exclude no-goal games which can't have leads)
    home_pays = np.sum(home_ever_led & ~no_goals_mask)
    away_pays = np.sum(away_ever_led & ~no_goals_mask)
    
    return float(home_pays) / n_sims, float(away_pays) / n_sims


# ========== Base Engine Class ==========

class BaseEngine:
    """
    Base class for 1UP pricing engines.
    
    All engines should inherit from this and implement calculate() method.
    """
    
    name: str = "Base"
    description: str = "Base engine class"
    
    def __init__(self, n_sims: int = 30000, match_minutes: int = 95, margin_pct: float = 0.05):
        """
        Initialize engine with simulation settings.
        
        Args:
            n_sims: Number of Monte Carlo simulations
            match_minutes: Match duration in minutes
            margin_pct: Margin to apply to output odds
        """
        self.n_sims = n_sims
        self.match_minutes = match_minutes
        self.margin_pct = margin_pct
    
    def calculate(self, markets: dict, bookmaker: str) -> dict:
        """
        Calculate 1UP odds from market data.
        
        Args:
            markets: Dictionary of market data
            bookmaker: 'sporty' or 'pawa'
        
        Returns:
            Dictionary with calculation results
        """
        raise NotImplementedError("Subclasses must implement calculate()")
    
    def _extract_and_validate_ou_markets(self, markets: dict) -> dict:
        """
        Extract and validate Over/Under market data from markets dictionary.

        This is the common validation logic used by most engines that need:
        - 1X2 odds (home, draw, away)
        - Total O/U line
        - Home O/U line
        - Away O/U line

        Args:
            markets: Dictionary with market data

        Returns:
            Dict with validated market data, or None if validation fails
            {
                'x1x2': (home_odds, draw_odds, away_odds),
                'total_ou': (line, over_odds, under_odds),
                'home_ou': (line, over_odds, under_odds),
                'away_ou': (line, over_odds, under_odds)
            }
        """
        # Extract market data
        x1x2 = markets.get('1x2')
        total_ou = markets.get('total_ou')
        home_ou = markets.get('home_ou')
        away_ou = markets.get('away_ou')

        # Check all required markets exist
        if not all([x1x2, total_ou, home_ou, away_ou]):
            return None

        # Unpack and validate 1X2
        home_1x2, draw_1x2, away_1x2 = x1x2
        if not all([home_1x2, draw_1x2, away_1x2]):
            return None

        # Unpack and validate Total O/U
        total_line, total_over, total_under = total_ou
        if not all([total_line, total_over, total_under]):
            return None

        # Unpack and validate Home O/U
        home_line, home_over, home_under = home_ou
        if not all([home_line, home_over, home_under]):
            return None

        # Unpack and validate Away O/U
        away_line, away_over, away_under = away_ou
        if not all([away_line, away_over, away_under]):
            return None

        return {
            'x1x2': (home_1x2, draw_1x2, away_1x2),
            'total_ou': (total_line, total_over, total_under),
            'home_ou': (home_line, home_over, home_under),
            'away_ou': (away_line, away_over, away_under)
        }

    def _prob_to_odds(self, prob: float) -> Tuple[float, float]:
        """
        Convert probability to fair and margin-adjusted odds.

        Returns:
            Tuple of (fair_odds, margin_odds)
        """
        if prob <= 0:
            return None, None
        fair = 1.0 / prob
        margin = fair * (1.0 - self.margin_pct)
        return fair, margin
    
    def _build_result(
        self,
        lambda_home: float,
        lambda_away: float,
        lambda_total: float,
        p_home_1up: float,
        p_away_1up: float,
        draw_odds: float,
        input_1x2: dict,
        extra: dict = None
    ) -> dict:
        """
        Build standardized result dictionary.
        """
        home_fair, home_margin = self._prob_to_odds(p_home_1up)
        away_fair, away_margin = self._prob_to_odds(p_away_1up)
        
        result = {
            'engine': self.name,
            'lambda_home': lambda_home,
            'lambda_away': lambda_away,
            'lambda_total': lambda_total,
            'p_home_1up': p_home_1up,
            'p_away_1up': p_away_1up,
            '1up_home_fair': home_fair,
            '1up_home_margin': home_margin,
            '1up_draw': draw_odds,
            '1up_away_fair': away_fair,
            '1up_away_margin': away_margin,
            'input_1x2': input_1x2,
        }
        
        if extra:
            result.update(extra)
        
        return result
