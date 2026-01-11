# Guide: Creating a New Engine

## Quick Start Template

Here's a minimal engine you can copy and customize:

```python
# src/engine/my_new_engine.py

from typing import Optional
from .base import BaseEngine, devig_three_way

class MyNewEngine(BaseEngine):
    """
    Your engine description here.

    This engine uses [your methodology] to calculate 1UP odds.
    """

    name = "MyNewEngine"
    description = "Brief description of what makes your engine unique"

    def __init__(self, n_sims: int = 30000, match_minutes: int = 95, margin_pct: float = 0.05):
        super().__init__(n_sims, match_minutes, margin_pct)
        # Add any engine-specific initialization

    def calculate(self, markets: dict, bookmaker: str) -> Optional[dict]:
        """
        Calculate 1UP odds from market data.

        Args:
            markets: Dict with market odds from _prepare_market_data
            bookmaker: 'sporty', 'pawa', or 'bet9ja'

        Returns:
            Dict with calculated results, or None if data insufficient
        """

        # Step 1: Extract required markets
        x1x2 = markets.get('1x2')
        total_ou = markets.get('total_ou')

        # Validate we have required data
        if not all([x1x2, total_ou]):
            return None

        home_1x2, draw_1x2, away_1x2 = x1x2
        total_line, total_over, total_under = total_ou

        if not all([home_1x2, draw_1x2, away_1x2]):
            return None

        # Step 2: Your calculation logic here
        # ... (infer lambdas, run simulation, etc.)

        lambda_home = 1.5  # Your calculation
        lambda_away = 1.2  # Your calculation
        lambda_total = 2.7  # Your calculation

        p_home_1up = 0.65  # Your calculated probability
        p_away_1up = 0.55  # Your calculated probability

        # Convert probabilities to odds
        fair_home = 1.0 / p_home_1up
        fair_away = 1.0 / p_away_1up
        fair_draw = draw_1x2  # Usually just use bookmaker's draw

        # Step 3: Return standardized result
        return self._build_result(
            lambda_home=lambda_home,
            lambda_away=lambda_away,
            lambda_total=lambda_total,
            p_home_1up=p_home_1up,
            p_away_1up=p_away_1up,
            draw_odds=fair_draw,
            input_1x2={'home': home_1x2, 'draw': draw_1x2, 'away': away_1x2}
        )
```

---

## Step-by-Step Integration

### 1. Create Your Engine File

Create `src/engine/my_new_engine.py` with the template above.

### 2. Export Your Engine

Edit `src/engine/__init__.py`:

```python
from .base import (
    devig_two_way,
    devig_three_way,
    poisson_sample,
    simulate_1up_probabilities,
    fit_lambda_from_ou_lines,
)
from .poisson_calibrated import CalibratedPoissonEngine
from .my_new_engine import MyNewEngine  # ADD THIS

__all__ = [
    'devig_two_way',
    'devig_three_way',
    'poisson_sample',
    'simulate_1up_probabilities',
    'fit_lambda_from_ou_lines',
    'CalibratedPoissonEngine',
    'MyNewEngine',  # ADD THIS
]
```

### 3. Register Your Engine in Runner

Edit `src/engine/runner.py`:

```python
from src.engine import CalibratedPoissonEngine, MyNewEngine  # Import both

class EngineRunner:
    def __init__(self, db: DatabaseManager, config: ConfigLoader = None):
        # ... existing code ...

        # Replace single engine with list of engines
        self.engines = [
            CalibratedPoissonEngine(**engine_params),
            MyNewEngine(**engine_params),
        ]

        logger.info(f"EngineRunner initialized with {len(self.engines)} engine(s)")
        for engine in self.engines:
            logger.info(f"  - {engine.name}")
```

### 4. Test Your Engine

```bash
# Test imports
python -c "from src.engine import MyNewEngine; print('Import OK')"

# Test engine calculation
python -c "
from src.engine import MyNewEngine
from src.db.manager import DatabaseManager
from src.config import ConfigLoader

config = ConfigLoader()
db = DatabaseManager(config.get_db_path())
db.connect()

# Get test data
markets = db.get_markets_for_event('sr:match:46511487')
print(f'Got {len(markets)} markets')

db.close()
"

# Run full test
python main.py --engines
```

---

## Available Input Markets

These are automatically prepared for you in the `markets` dict:

### Standard Markets (Always Available)

```python
markets = {
    # 1X2 odds (Home, Draw, Away)
    '1x2': (2.10, 3.40, 3.20),

    # Total Over/Under (Line, Over, Under)
    'total_ou': (2.5, 1.85, 2.05),

    # Home Team O/U (Line, Over, Under)
    'home_ou': (0.5, 1.40, 3.10),

    # Away Team O/U (Line, Over, Under)
    'away_ou': (0.5, 1.55, 2.50),

    # Both Teams To Score (Yes, No)
    'btts': (1.75, 2.10),

    # Asian Handicap dict {line: (home_odds, away_odds)}
    'asian_handicap': {
        -1.0: (1.95, 1.95),
        -0.5: (1.80, 2.10),
        0.0: (2.50, 1.65),
        +0.5: (2.80, 1.45),
        +1.0: (3.20, 1.35),
    },

    # First Team to Score (Home, NoGoal, Away)
    'first_goal': (2.50, 5.00, 3.20),

    # Lead by 1 markets (Yes, No)
    'home_lead1': (1.90, 1.95),
    'away_lead1': (2.10, 1.85),
}
```

### Adding New Markets

If you need a market that's not currently available:

**Option 1: Add to runner.py**

Edit `_prepare_market_data` in `src/engine/runner.py`:

```python
def _prepare_market_data(self, markets: list[dict], bookmaker: str) -> dict:
    # ... existing extractions ...

    # Add your new market
    your_market = self._get_your_market_odds(markets, bookmaker)

    return {
        # ... existing markets ...
        'your_market': your_market,
    }

def _get_your_market_odds(self, markets: list[dict], bookmaker: str) -> tuple:
    """Extract your market odds."""
    m = self._get_market_odds(markets, "Market Name", "specifier")
    if not m:
        return None, None
    odds = m[bookmaker]
    return odds['outcome_1'], odds['outcome_2']
```

**Option 2: Query directly in your engine**

```python
def calculate(self, markets: dict, bookmaker: str):
    # Use the _get_market_odds helper from runner
    # (you'd need to pass the raw markets list to the engine)
    pass
```

---

## Helper Functions You Can Use

Import from `src.engine.base`:

### De-vigging Functions

```python
from src.engine.base import devig_two_way, devig_three_way

# Two-way market (e.g., Over/Under)
p_over = devig_two_way(odds_over, odds_under)
# Returns: Fair probability of Over

# Three-way market (e.g., 1X2)
p_home, p_draw, p_away = devig_three_way(home_odds, draw_odds, away_odds)
# Returns: Fair probabilities
```

### Lambda Fitting

```python
from src.engine.base import fit_lambda_from_ou_lines

# Single O/U line
lambda_home = fit_lambda_from_ou_lines([(0.5, 1.40, 3.10)])

# Multiple O/U lines (more accurate!)
lines_odds = [
    (0.5, 1.40, 3.10),  # Line 0.5
    (1.5, 2.80, 1.45),  # Line 1.5
    (2.5, 6.50, 1.12),  # Line 2.5
]
lambda_home = fit_lambda_from_ou_lines(lines_odds)
# Returns: Poisson lambda that best fits all lines
```

### Monte Carlo Simulation

```python
from src.engine.base import simulate_1up_probabilities

p_home_1up, p_away_1up = simulate_1up_probabilities(
    lambda_home=1.5,
    lambda_away=1.2,
    n_sims=30000,
    match_minutes=95
)
# Returns: Probabilities that each team leads by 1+ at any point
```

### Poisson Sampling

```python
from src.engine.base import poisson_sample

goals = poisson_sample(lambda_param=1.5)
# Returns: Random integer from Poisson(1.5)
```

---

## Required Output Format

Your `calculate()` method **must** return a dict with these keys:

```python
{
    # Engine identification
    'engine': 'MyEngineName',  # string

    # Lambda parameters (expected goals)
    'lambda_home': 1.45,       # float, > 0
    'lambda_away': 1.23,       # float, > 0
    'lambda_total': 2.68,      # float, > 0

    # Calculated probabilities
    'p_home_1up': 0.65,        # float, 0-1
    'p_away_1up': 0.55,        # float, 0-1

    # Fair odds (1/probability with margin)
    '1up_home_fair': 1.54,     # float, >= 1.0
    '1up_away_fair': 1.82,     # float, >= 1.0
    '1up_draw': 3.40,          # float, >= 1.0
}
```

**Optional extras:**

You can add extra keys for debugging/analysis:

```python
{
    # ... required keys above ...

    # Optional extras
    'p_home_win': 0.52,         # Win probability
    'p_draw': 0.28,             # Draw probability
    'p_away_win': 0.20,         # Win probability
    'confidence': 0.85,         # Your confidence score
    'method': 'neural_network',  # Which method you used
    # ... anything else you want to track
}
```

These extras will be ignored by the storage layer but can be useful for logging.

---

## Testing Your Engine

### Unit Test

```python
# test_my_engine.py
from src.engine import MyNewEngine

def test_basic_calculation():
    engine = MyNewEngine(n_sims=10000, match_minutes=95, margin_pct=0.0)

    # Prepare test data
    markets = {
        '1x2': (2.10, 3.40, 3.20),
        'total_ou': (2.5, 1.85, 2.05),
        'home_ou': (0.5, 1.40, 3.10),
        'away_ou': (0.5, 1.55, 2.50),
    }

    result = engine.calculate(markets, 'sporty')

    # Check required keys
    assert result is not None
    assert 'engine' in result
    assert 'lambda_home' in result
    assert 'p_home_1up' in result
    assert '1up_home_fair' in result

    # Check value ranges
    assert 0 < result['lambda_home'] < 5
    assert 0 < result['p_home_1up'] < 1
    assert result['1up_home_fair'] >= 1.0

    print("✓ All tests passed!")
    print(f"Result: {result}")

if __name__ == "__main__":
    test_basic_calculation()
```

Run with:
```bash
python test_my_engine.py
```

### Integration Test

```python
# test_integration.py
from src.db.manager import DatabaseManager
from src.config import ConfigLoader
from src.engine.runner import EngineRunner

config = ConfigLoader()
db = DatabaseManager(config.get_db_path())
db.connect()

runner = EngineRunner(db, config)

# Test on one event
result = runner.run_event('sr:match:46511487')
print(f"Stored {result} calculations")

db.close()
```

---

## Common Patterns

### Pattern 1: Use Multiple O/U Lines

```python
def calculate(self, markets: dict, bookmaker: str):
    # Extract all available O/U lines for better lambda estimation
    total_ou = markets.get('total_ou')

    # If total_ou is a list of multiple lines
    if isinstance(total_ou, list):
        lambda_total = fit_lambda_from_ou_lines(total_ou)
    else:
        # Single line
        lambda_total = fit_lambda_from_ou_lines([total_ou])
```

### Pattern 2: Graceful Degradation

```python
def calculate(self, markets: dict, bookmaker: str):
    # Try to use preferred markets
    asian_handicap = markets.get('asian_handicap')

    if asian_handicap:
        # Use handicap for better estimation
        lambda_home, lambda_away = self._infer_from_handicap(asian_handicap)
    else:
        # Fall back to basic method
        x1x2 = markets.get('1x2')
        lambda_home, lambda_away = self._infer_from_1x2(x1x2)
```

### Pattern 3: Combine Multiple Inputs

```python
def calculate(self, markets: dict, bookmaker: str):
    # Get estimates from multiple sources
    x1x2 = markets.get('1x2')
    total_ou = markets.get('total_ou')
    home_ou = markets.get('home_ou')
    away_ou = markets.get('away_ou')

    # Method 1: From team totals
    lambda_home_v1 = fit_lambda_from_ou_lines([home_ou])
    lambda_away_v1 = fit_lambda_from_ou_lines([away_ou])

    # Method 2: From 1X2
    lambda_home_v2, lambda_away_v2 = self._infer_from_1x2(x1x2)

    # Combine with weights
    lambda_home = 0.7 * lambda_home_v1 + 0.3 * lambda_home_v2
    lambda_away = 0.7 * lambda_away_v1 + 0.3 * lambda_away_v2
```

---

## Debugging Tips

### Print Market Data

```python
def calculate(self, markets: dict, bookmaker: str):
    print(f"\n=== {self.name} - {bookmaker} ===")
    for key, value in markets.items():
        print(f"{key}: {value}")

    # ... rest of calculation
```

### Log Intermediate Steps

```python
def calculate(self, markets: dict, bookmaker: str):
    import logging
    logger = logging.getLogger(__name__)

    lambda_home = self._calculate_lambda_home(markets)
    logger.info(f"Calculated lambda_home: {lambda_home}")

    # ... rest of calculation
```

### Compare to Existing Engine

```python
# Run both engines on same data
from src.engine import CalibratedPoissonEngine, MyNewEngine

old_engine = CalibratedPoissonEngine()
new_engine = MyNewEngine()

old_result = old_engine.calculate(markets, 'sporty')
new_result = new_engine.calculate(markets, 'sporty')

print(f"Old fair home: {old_result['1up_home_fair']}")
print(f"New fair home: {new_result['1up_home_fair']}")
print(f"Difference: {new_result['1up_home_fair'] - old_result['1up_home_fair']}")
```

---

## Next Steps

1. **Copy the template** → Create your engine file
2. **Implement calculate()** → Add your calculation logic
3. **Test with dummy data** → Verify output format
4. **Register in runner** → Add to engine list
5. **Test with real data** → Run `python main.py --engines`
6. **Analyze results** → Compare to actual odds
7. **Iterate and improve** → Refine your methodology

Need help with any step? Let me know!
