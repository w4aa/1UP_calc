"""
Lead1 Calibrated Engine

1UP pricing engine that uses Sportybet's "Lead by 1 Goal" markets
to calibrate the model.

Inputs used:
- 1X2 market (for draw odds)
- Total O/U market (match total)
- Home Team O/U market
- Away Team O/U market
- Home Lead by 1 market (Sportybet only - market 60303)
- Away Lead by 1 market (Sportybet only - market 60306)

Calibration approach:
1. Start with Poisson lambdas from O/U markets
2. Use "Lead by 1" market probabilities to calibrate the simulation
3. Adjust lambdas so model matches market's lead probability
"""

from typing import Optional, Tuple
import math
from .base import (
    BaseEngine,
    devig_two_way,
    devig_three_way,
    infer_lambda_from_ou_market,
    simulate_1up_probabilities,
    poisson_sample,
)
import random


def simulate_lead1_probabilities(
    lambda_home: float,
    lambda_away: float,
    n_sims: int = 30000,
    match_minutes: int = 95
) -> Tuple[float, float]:
    """
    Simulate probability that each team leads by exactly 1 goal at some point.
    
    This is slightly different from 1UP which is "ever leads by >= 1".
    Here we check "ever leads by >= 1" which is what 1UP uses.
    
    Returns:
        Tuple of (p_home_lead1, p_away_lead1)
    """
    home_leads = 0
    away_leads = 0
    
    for _ in range(n_sims):
        n_home = poisson_sample(lambda_home)
        n_away = poisson_sample(lambda_away)
        
        events = []
        for _ in range(n_home):
            t = random.uniform(0, match_minutes)
            events.append((t, 'H'))
        for _ in range(n_away):
            t = random.uniform(0, match_minutes)
            events.append((t, 'A'))
        
        events.sort(key=lambda x: x[0])
        
        diff = 0
        home_ever_led = False
        away_ever_led = False
        
        for _, team in events:
            if team == 'H':
                diff += 1
            else:
                diff -= 1
            
            if diff > 0:
                home_ever_led = True
            if diff < 0:
                away_ever_led = True
        
        if home_ever_led:
            home_leads += 1
        if away_ever_led:
            away_leads += 1
    
    return home_leads / n_sims, away_leads / n_sims


def calibrate_lambda_to_lead_prob(
    target_prob: float,
    other_lambda: float,
    is_home: bool,
    n_sims: int = 10000,
    match_minutes: int = 95,
    tolerance: float = 0.005,
    max_iterations: int = 20
) -> float:
    """
    Find lambda for one team such that P(team ever leads) matches target.
    
    Uses binary search to find the lambda value.
    
    Args:
        target_prob: Target probability for "team ever leads"
        other_lambda: Lambda for the opposing team (fixed)
        is_home: True if calibrating home lambda, False for away
        n_sims: Simulations per iteration
        match_minutes: Match duration
        tolerance: Acceptable error in probability
        max_iterations: Max binary search iterations
    
    Returns:
        Calibrated lambda value
    """
    lam_low = 0.1
    lam_high = 4.0
    
    for _ in range(max_iterations):
        lam_mid = 0.5 * (lam_low + lam_high)
        
        if is_home:
            p_home, _ = simulate_lead1_probabilities(lam_mid, other_lambda, n_sims, match_minutes)
            p_current = p_home
        else:
            _, p_away = simulate_lead1_probabilities(other_lambda, lam_mid, n_sims, match_minutes)
            p_current = p_away
        
        if abs(p_current - target_prob) < tolerance:
            break
        
        if p_current < target_prob:
            lam_low = lam_mid
        else:
            lam_high = lam_mid
    
    return 0.5 * (lam_low + lam_high)


class Lead1CalibratedEngine(BaseEngine):
    """
    1UP engine calibrated using Sportybet's "Lead by 1" markets.
    
    Uses the actual market probability for "team leads by 1 at any point"
    to validate and adjust the Poisson model.
    """
    
    name = "Lead1-Calibrated"
    description = "Calibrates using Sporty 'Lead by 1' markets"
    
    def calculate(self, markets: dict, bookmaker: str) -> Optional[dict]:
        """
        Calculate 1UP odds using Lead by 1 market calibration.
        
        Args:
            markets: Dictionary with market data:
                - '1x2': (home, draw, away) odds
                - 'total_ou': (line, over, under) odds
                - 'home_ou': (line, over, under) odds
                - 'away_ou': (line, over, under) odds
                - 'home_lead1': (yes, no) odds (Sportybet market 60303)
                - 'away_lead1': (yes, no) odds (Sportybet market 60306)
            bookmaker: 'sporty' or 'pawa'
        
        Returns:
            Dictionary with calculation results or None if missing data
        """
        # Extract required markets
        x1x2 = markets.get('1x2')
        total_ou = markets.get('total_ou')
        home_ou = markets.get('home_ou')
        away_ou = markets.get('away_ou')
        
        # Lead by 1 markets (Sportybet only, but used for both calculations)
        home_lead1 = markets.get('home_lead1')
        away_lead1 = markets.get('away_lead1')
        
        # Validate core data
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
        
        # Step 1: Get base lambdas from O/U markets
        p_home_win, p_draw, p_away_win = devig_three_way(home_1x2, draw_1x2, away_1x2)
        
        lambda_home_raw = infer_lambda_from_ou_market(home_line, home_over, home_under)
        lambda_away_raw = infer_lambda_from_ou_market(away_line, away_over, away_under)
        split_sum = lambda_home_raw + lambda_away_raw
        
        lambda_total = infer_lambda_from_ou_market(total_line, total_over, total_under)
        
        if split_sum > 0:
            factor = lambda_total / split_sum
        else:
            factor = 1.0
        
        lambda_home = lambda_home_raw * factor
        lambda_away = lambda_away_raw * factor
        
        # Step 2: If Lead by 1 markets available, use them to calibrate
        calibration_applied = False
        p_lead1_home_market = None
        p_lead1_away_market = None
        
        if home_lead1 and home_lead1[0] and home_lead1[1]:
            # De-vig to get fair probability
            p_lead1_home_market = devig_two_way(home_lead1[0], home_lead1[1])
            calibration_applied = True
        
        if away_lead1 and away_lead1[0] and away_lead1[1]:
            p_lead1_away_market = devig_two_way(away_lead1[0], away_lead1[1])
            calibration_applied = True
        
        # Step 3: Calibrate lambdas using Lead by 1 market probabilities
        # We adjust lambdas to match the market's lead probabilities
        if calibration_applied:
            # Calculate what our model predicts for lead probabilities
            p_home_lead_model, p_away_lead_model = simulate_lead1_probabilities(
                lambda_home, lambda_away, n_sims=10000, match_minutes=self.match_minutes
            )
            
            # Apply scaling factor based on market vs model discrepancy
            if p_lead1_home_market and p_home_lead_model > 0:
                # Scale lambda to adjust lead probability
                # Higher lambda = higher lead probability
                home_scale = p_lead1_home_market / p_home_lead_model
                # Clamp scaling to reasonable range
                home_scale = max(0.7, min(1.3, home_scale))
                lambda_home *= home_scale
            
            if p_lead1_away_market and p_away_lead_model > 0:
                away_scale = p_lead1_away_market / p_away_lead_model
                away_scale = max(0.7, min(1.3, away_scale))
                lambda_away *= away_scale
            
            # Update total after calibration
            lambda_total = lambda_home + lambda_away
        
        # Step 4: Run final Monte Carlo simulation for 1UP probabilities
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
                'calibration_applied': calibration_applied,
                'p_lead1_home_market': p_lead1_home_market,
                'p_lead1_away_market': p_lead1_away_market,
            }
        )
