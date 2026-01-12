"""
1UP Engine Package

Contains engines for calculating 1UP 1X2 markets.

Engines:
- FTSCalibratedDPEngine: FTS-anchored DP with post-FTS calibration (provider-aware)
"""

from .base import (
    devig_two_way,
    devig_three_way,
    poisson_sample,
    simulate_1up_probabilities,
    fit_lambda_from_ou_lines,
)
from .fts_calibrated_dp import FTSCalibratedDPEngine

__all__ = [
    'devig_two_way',
    'devig_three_way',
    'poisson_sample',
    'simulate_1up_probabilities',
    'fit_lambda_from_ou_lines',
    'FTSCalibratedDPEngine',
]
