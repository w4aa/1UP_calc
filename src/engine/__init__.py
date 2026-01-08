"""
1UP Engine Package

Contains different engine implementations for calculating 1UP 1X2 markets.
Each engine uses different input markets and calibration methods.

Engines:
- base: Core Monte Carlo simulation engine (base class)
- poisson: Uses O/U markets to infer Poisson lambdas (original)
- poisson_calibrated: Poisson with empirical underdog correction
- lead1_calibrated: Uses Sportybet's "Lead by 1" markets to calibrate
- first_goal: Uses "First Team to Score" market to calibrate
- handicap: Uses Asian Handicap market to calibrate
- btts: Uses GG/NG (Both Teams to Score) market to calibrate
"""

from .base import (
    devig_two_way,
    devig_three_way,
    poisson_sample,
    simulate_1up_probabilities,
)
from .poisson import PoissonEngine
from .poisson_calibrated import CalibratedPoissonEngine
from .lead1_calibrated import Lead1CalibratedEngine
from .first_goal import FirstGoalEngine
from .handicap import HandicapEngine

from .btts import BTTSEngine
from .supremacy_poisson import SupremacyPoissonEngine
# NOTE: CalibratedSupremacyPoissonEngine temporarily disabled due to dependency on removed empirical_underdog_correction
# TODO: Update to use new probability-level correction approach from CalibratedPoissonEngine
# from .calibrated_supremacy_poisson import CalibratedSupremacyPoissonEngine

__all__ = [
    'devig_two_way',
    'devig_three_way',
    'poisson_sample',
    'simulate_1up_probabilities',
    'PoissonEngine',
    'CalibratedPoissonEngine',
    'Lead1CalibratedEngine',
    'FirstGoalEngine',
    'HandicapEngine',
    'BTTSEngine',
    'SupremacyPoissonEngine',
    # 'CalibratedSupremacyPoissonEngine',  # Temporarily disabled
]
