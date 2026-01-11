# 1UP Calculator

A sophisticated betting odds calculation system that scrapes odds from multiple bookmakers, calculates fair 1UP (early payout) odds using Poisson-based engines, and analyzes engine performance to find value bets.

## Table of Contents

- [Overview](#overview)
- [Quick Start](#quick-start)
- [Architecture](#architecture)
- [Project Structure](#project-structure)
- [Data Flow](#data-flow)
- [Engines](#engines)
- [Usage](#usage)
- [Configuration](#configuration)
- [Testing](#testing)
- [Development Guide](#development-guide)
- [License](#license)

---

## Overview

The 1UP Calculator performs the following:

1. **Scrapes** odds from 3 bookmakers:
   - **Sportybet** (Playwright browser automation)
   - **Betpawa** (HTTP/API)
   - **Bet9ja** (HTTP/API)

2. **Stores** unified odds in SQLite database
   - All 3 bookmakers' odds in a single table row for easy comparison
   - Historical snapshots for time-series analysis
   - Change detection (only scrapes when 1X2 odds change)

3. **Calculates** fair 1UP odds using two engines:
   - **CalibratedPoissonEngine**: Poisson with empirical underdog correction
   - **FTSCalibratedDPEngine**: FTS-anchored DP with post-FTS calibration

4. **Compares** calculated odds vs actual bookmaker odds
   - Identifies value bets
   - Analyzes engine performance (MAE, probability errors, log-odds errors)
   - Generates comprehensive reports (CSV/HTML)

---

## Quick Start

### 1. Setup Environment

```powershell
# Create virtual environment
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# Install dependencies
pip install -r requirements.txt

# Install Playwright browsers (for Sportybet scraping)
playwright install
```

### 2. Run the System

```powershell
# Full pipeline (scrape + engines + analysis)
python main.py --analyze

# Scrape only
python main.py --scrape

# Engines only (on existing data)
python main.py --engines

# Re-run engines without scraping
python src/run_engines.py
```

### 3. Analyze Results

```powershell
# Full analysis with default settings
python analyze_engines.py

# Analyze specific bookmaker
python analyze_engines.py --bookmaker sporty

# Analyze specific engine
python analyze_engines.py --engine FTS-Calibrated-DP

# Apply margin to fair odds
python analyze_engines.py --margin 0.06

# Compare engines side-by-side
python compare_engines.py

# Generate HTML/CSV reports
python generate_engine_report.py
```

---

## Architecture

### System Components

```
┌─────────────────────────────────────────────────────────────────┐
│                    Configuration Layer                           │
│  (tournaments.yaml, markets.yaml, settings.yaml, engine.yaml)   │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│                    Scraping Layer                                │
│  ┌──────────────┬──────────────┬──────────────┐                 │
│  │  Sportybet   │   Betpawa    │   Bet9ja     │                 │
│  │  (Playwright)│   (HTTP)     │   (HTTP)     │                 │
│  └──────────────┴──────────────┴──────────────┘                 │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│                    Database Layer (SQLite)                       │
│  • events - Match records                                        │
│  • markets - Unified odds (all 3 bookmakers per row)            │
│  • market_snapshots - Historical snapshots                       │
│  • engine_calculations - Engine results                          │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│                    Engine Layer                                  │
│  ┌─────────────────────────┬───────────────────────────┐        │
│  │  CalibratedPoisson      │  FTSCalibratedDP          │        │
│  │  Engine                 │  Engine                   │        │
│  └─────────────────────────┴───────────────────────────┘        │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│                    Analysis Layer                                │
│  • MAE (probability and odds scales)                             │
│  • Log-odds errors                                               │
│  • Engine comparison                                             │
│  • Report generation                                             │
└─────────────────────────────────────────────────────────────────┘
```

### Key Design Principles

#### 1. Unified Data Model

All bookmakers' odds are stored in **one row** per market:

```sql
CREATE TABLE markets (
    sportradar_id TEXT,
    market_name TEXT,  -- "1X2", "Over/Under", "BTTS", etc.
    specifier TEXT,    -- "2.5" for O/U 2.5, "" for 1X2

    -- Sportybet odds
    sporty_outcome_1_odds REAL,
    sporty_outcome_2_odds REAL,
    sporty_outcome_3_odds REAL,

    -- Betpawa odds
    pawa_outcome_1_odds REAL,
    pawa_outcome_2_odds REAL,
    pawa_outcome_3_odds REAL,

    -- Bet9ja odds
    bet9ja_outcome_1_odds REAL,
    bet9ja_outcome_2_odds REAL,
    bet9ja_outcome_3_odds REAL
);
```

**Benefits:**
- Easy cross-bookmaker comparison (no joins needed)
- Fast queries
- Simple data model

#### 2. Parallel Processing

- **Scraping**: 3 bookmakers scrape in parallel
- **Engines**: ThreadPoolExecutor for parallel event processing
- **Tournaments**: Parallel tournament scraping

#### 3. Change Detection

Only scrapes when 1X2 odds change:
- Reduces unnecessary API calls
- Saves bandwidth
- Focuses on meaningful updates

---

## Project Structure

```
1UP_calc/
├── config/
│   ├── settings.yaml         # Scraper settings, DB path, concurrency
│   ├── engine.yaml           # Engine enable/disable, simulation params
│   ├── markets.yaml          # Market ID mappings between bookmakers
│   └── tournaments.yaml      # Tournament definitions (9 tournaments)
│
├── src/
│   ├── config.py             # Configuration loader
│   ├── unified_scraper.py    # Scraper orchestrator
│   ├── run_engines.py        # Engine-only runner
│   │
│   ├── db/
│   │   ├── manager.py        # Database operations
│   │   └── models.py         # Data models
│   │
│   ├── engine/
│   │   ├── base.py           # Base utilities (devigging, Poisson, Monte Carlo)
│   │   ├── poisson_calibrated.py      # Poisson engine (ACTIVE)
│   │   ├── fts_calibrated_dp.py       # FTS engine (ACTIVE)
│   │   └── runner.py         # Engine orchestration
│   │
│   └── scraper/
│       ├── sporty/           # Sportybet scraper (Playwright)
│       ├── pawa/             # Betpawa scraper (HTTP)
│       └── bet9ja/           # Bet9ja scraper (HTTP)
│
├── tests/                    # All test files
│   ├── test_analyze.py
│   ├── test_analyze_engines.py
│   ├── test_fts_engine.py
│   ├── test_runner.py
│   └── test_system.py
│
├── data/
│   └── datas.db             # SQLite database
│
├── reports/                 # Generated analysis files
│
├── main.py                  # Main entry point
├── analyze_engines.py       # Engine analysis tool
├── compare_engines.py       # Engine comparison
├── generate_engine_report.py  # Report generator
├── sanity_check.py          # DB validation
└── requirements.txt         # Python dependencies
```

---

## Data Flow

### Complete Flow: From Scraping to Analysis

```
┌─────────────────────────────────────────────────────────────────┐
│  PHASE 1: SCRAPING (main.py → unified_scraper.py)               │
└─────────────────────────────────────────────────────────────────┘
                              ↓
    ┌──────────────────┬────────────┬──────────────────┐
    ↓                  ↓            ↓                  ↓
Sportybet          Betpawa      Bet9ja         Tournaments
(Browser)          (HTTP)       (HTTP)           Config
    │                  │            │                  │
    └──────────────────┴────────────┴──────────────────┘
                              ↓
              SQLite Database (datas.db)
              ┌─────────────────────────────┐
              │ events table                │
              │ markets table (KEY!)        │
              │ market_snapshots table      │
              └─────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│  PHASE 2: ENGINE CALCULATION (engine/runner.py)                 │
└─────────────────────────────────────────────────────────────────┘
                              ↓
        For each matched event:
          For each bookmaker (sporty, pawa, bet9ja):
            1. Get all markets from DB
            2. Extract needed odds (1X2, O/U, BTTS, FTS)
            3. Run engine calculation
            4. Store result in engine_calculations table
                              ↓
              engine_calculations table
              ┌─────────────────────────────┐
              │ - sportradar_id             │
              │ - engine_name               │
              │ - bookmaker                 │
              │ - lambda_home/away/total    │
              │ - p_home_1up, p_away_1up    │
              │ - fair_home, fair_away      │
              │ - actual_sporty_home/away   │
              │ - actual_bet9ja_home/away   │
              └─────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│  PHASE 3: ANALYSIS (analyze_engines.py, compare_engines.py)    │
└─────────────────────────────────────────────────────────────────┘
                              ↓
              Analysis Metrics:
              • Probability MAE (primary metric)
              • Log-odds MAE (stable metric)
              • Error by lambda bins
              • Engine comparison
                              ↓
              Reports (CSV/HTML)
```

### Market Data Preparation

The runner extracts specific markets from the database and prepares them for engines:

```python
# Input: Raw markets from DB (all bookmakers in one row)
markets_raw = [
    {
        'market_name': '1X2',
        'specifier': '',
        'sporty_outcome_1_odds': 2.10,  # Home
        'sporty_outcome_2_odds': 3.40,  # Draw
        'sporty_outcome_3_odds': 3.20,  # Away
        'pawa_outcome_1_odds': 2.05,
        'pawa_outcome_2_odds': 3.50,
        'pawa_outcome_3_odds': 3.30,
        # ... bet9ja odds
    },
    {
        'market_name': 'Over/Under',
        'specifier': '2.5',
        'sporty_outcome_1_odds': 1.85,  # Over
        'sporty_outcome_2_odds': 2.05,  # Under
        # ... other bookmakers
    },
    # ... more markets
]

# Output: Structured dict for engines (bookmaker-specific)
prepared_data = {
    '1x2': (2.10, 3.40, 3.20),  # Home, Draw, Away
    'total_ou': (2.5, 1.85, 2.05),  # Line, Over, Under
    'home_ou': (0.5, 1.40, 3.10),
    'away_ou': (0.5, 1.55, 2.50),
    'btts': (1.75, 2.10),  # Yes, No
    'first_goal': {
        'sporty': (2.50, 5.00, 3.20),  # Home, NoGoal, Away
        'bet9ja': (2.40, 5.20, 3.30),
    },
    'asian_handicap': {
        -1.0: (1.95, 1.95),  # Home -1, Away +1
        0.0: (2.50, 1.65),
    }
}
```

---

## Engines

### 1. CalibratedPoissonEngine

**Methodology:**
- De-vigs 1X2 odds to get fair win/draw/loss probabilities
- Infers Poisson lambdas from Over/Under markets
- Optimizes supremacy parameter to match 1X2 probabilities
- Runs Monte Carlo simulation (30,000 simulations)
- Applies empirical underdog correction

**Strengths:**
- Works with minimal market requirements (1X2 + O/U)
- Well-tested and stable
- Good for Bet9ja (which lacks consistent FTS markets)

**Performance:**
- Bet9ja: MAE 0.076 (Home), 0.067 (Away)
- Sporty: MAE 0.082 (Home), 0.077 (Away)
- Pawa: MAE 0.070 (Home), 0.063 (Away)

### 2. FTSCalibratedDPEngine

**Methodology:**
- Anchors to First Team To Score (FTS) odds for early scoring dynamics
- Uses Dynamic Programming instead of Monte Carlo (deterministic)
- Applies post-FTS calibration (logit transform)
- Provider-aware: Betpawa uses Sportybet FTS (same odds provider)

**Strengths:**
- **Excellent for Sporty/Pawa** (7-8x better than Poisson)
- Deterministic (no random variation)
- Fast (~20% faster than Monte Carlo)

**Performance:**
- Sporty: MAE 0.011 (Home), 0.009 (Away) ✓ Excellent
- Pawa: MAE 0.010 (Home), 0.009 (Away) ✓ Excellent
- Bet9ja: MAE 0.262 (Home), 0.377 (Away) ✗ Poor (FTS structure issues)

**Key Feature - Provider Awareness:**
```python
# The engine explicitly knows Betpawa uses Sportybet FTS
if bookmaker == "pawa":
    use_fts_from = "sporty"  # Same odds provider
elif bookmaker == "sporty":
    use_fts_from = "sporty"
elif bookmaker == "bet9ja":
    use_fts_from = "bet9ja"
```

### Engine Comparison

| Aspect | CalibratedPoisson | FTSCalibratedDP |
|--------|-------------------|-----------------|
| **Input Markets** | 1X2 + O/U (all lines) | 1X2 + O/U 2.5 + FTS |
| **Scoring Share** | From O/U team totals | Overridden by FTS |
| **Calculation** | Monte Carlo (30k sims) | DP (deterministic) |
| **Calibration** | Empirical underdog factors | Post-FTS logit transform |
| **Provider Aware** | No | Yes (Pawa uses Sporty FTS) |
| **Speed** | ~0.25s per match | ~0.2s per match |
| **Best For** | Bet9ja | Sportybet, Betpawa |

---

## Usage

### Command Line Options

#### main.py

```bash
# Full pipeline
python main.py                    # Scrape + engines
python main.py --analyze          # Scrape + engines + analysis
python main.py --force            # Force full scrape (ignore change detection)

# Individual phases
python main.py --scrape           # Scrape only
python main.py --engines          # Engines only
```

#### analyze_engines.py

```bash
# Full analysis
python analyze_engines.py

# Filter by bookmaker
python analyze_engines.py --bookmaker sporty
python analyze_engines.py --bookmaker pawa
python analyze_engines.py --bookmaker bet9ja

# Filter by engine
python analyze_engines.py --engine "Poisson-Calibrated"
python analyze_engines.py --engine "FTS-Calibrated-DP"

# Apply margin to fair odds
python analyze_engines.py --margin 0.06  # 6% margin

# Output options
python analyze_engines.py --no-csv       # Don't save CSV
python analyze_engines.py --output-dir reports  # Custom output dir
```

#### compare_engines.py

```bash
# Compare all engines
python compare_engines.py

# Compare specific bookmaker
python compare_engines.py --bookmaker sporty
```

#### generate_engine_report.py

```bash
# Generate HTML/CSV reports
python generate_engine_report.py

# Custom output directory
python generate_engine_report.py --output-dir reports
```

### Programmatic Usage

```python
from src.config import ConfigLoader
from src.db.manager import DatabaseManager
from src.engine.runner import EngineRunner

# Setup
config = ConfigLoader()
db = DatabaseManager(config.get_db_path())
db.connect()

# Run engines
runner = EngineRunner(db, config)
result = runner.run_all_events()  # Process all matched events
print(f"Stored {result} calculations")

# Or run single event
runner.run_event('sr:match:46511487')

db.close()
```

---

## Configuration

### config/settings.yaml

```yaml
scraper:
  headless: true
  timeout_ms: 30000
  max_retries: 3
  concurrent:
    pawa_events: 10
    sporty_events: 10
    bet9ja_events: 10
    tournaments: 3

database:
  path: data/datas.db
```

### config/engine.yaml

```yaml
engines:
  enabled:
    - CalibratedPoissonEngine
    - FTSCalibratedDPEngine

simulation:
  n_sims: 50000
  match_minutes: 95

parallel:
  max_workers: 4  # CPU cores for parallel processing
```

### config/tournaments.yaml

9 tournaments configured:
- AFCON
- Premier League
- La Liga
- Serie A
- Bundesliga
- Ligue 1
- Champions League
- Europa League
- FA Cup

Each tournament maps Sportradar IDs to Betpawa and Bet9ja IDs.

### config/markets.yaml

Maps market names between bookmakers:
- 1X2 (Match Winner)
- Over/Under (20+ lines)
- BTTS (Both Teams To Score)
- Asian Handicap
- First Team To Score (FTS)
- Home/Away Team Totals
- Lead by 1/2
- 1UP/2UP

---

## Testing

### Run All Tests

```bash
# Run all tests in tests/ directory
cd tests
python test_system.py
python test_fts_engine.py
python test_runner.py
python test_analyze.py
python test_analyze_engines.py
```

### Unit Tests

```bash
# Test FTS engine
python tests/test_fts_engine.py

# Test analysis functions
python tests/test_analyze_engines.py
```

### Integration Tests

```bash
# Test full system
python tests/test_system.py

# Test engine runner
python tests/test_runner.py
```

### Validation

```bash
# Database integrity check
python sanity_check.py
```

Expected output:
```
======================================================================
  SANITY CHECK - 1UP CALCULATOR
======================================================================

[1] DATABASE STATISTICS
----------------------------------------------------------------------
  Total Events:          145
  Matched Events:        145
  Total Markets:         6031
  Matched Markets:       2551

[2] ENGINE CALCULATIONS
----------------------------------------------------------------------
  Total Calculations:    5516
  With Session ID:       5516 (100.0%)

[3] DATA CONSISTENCY CHECKS
----------------------------------------------------------------------
  Orphaned Calculations: 0 ✓
  Orphaned Snapshots:    0 ✓
```

---

## Development Guide

### Creating a New Engine

1. **Create engine file** in `src/engine/your_engine.py`:

```python
from typing import Optional
from .base import BaseEngine, devig_three_way

class YourEngine(BaseEngine):
    """Your engine description."""

    name = "YourEngine"
    description = "Brief description"

    def calculate(self, markets: dict, bookmaker: str) -> Optional[dict]:
        """Calculate 1UP odds from market data."""

        # Extract required markets
        x1x2 = markets.get('1x2')
        if not x1x2:
            return None

        # Your calculation logic
        lambda_home = 1.5  # Your calculation
        lambda_away = 1.2
        p_home_1up = 0.65
        p_away_1up = 0.55

        # Return standardized result
        return self._build_result(
            lambda_home=lambda_home,
            lambda_away=lambda_away,
            lambda_total=lambda_home + lambda_away,
            p_home_1up=p_home_1up,
            p_away_1up=p_away_1up,
            draw_odds=x1x2[1],  # Use bookmaker's draw odds
            input_1x2={'home': x1x2[0], 'draw': x1x2[1], 'away': x1x2[2]}
        )
```

2. **Export engine** in `src/engine/__init__.py`:

```python
from .your_engine import YourEngine

__all__ = [
    # ... existing exports
    'YourEngine',
]
```

3. **Register in runner** in `src/engine/runner.py`:

```python
from src.engine import CalibratedPoissonEngine, FTSCalibratedDPEngine, YourEngine

self.engines = [
    CalibratedPoissonEngine(**engine_params),
    FTSCalibratedDPEngine(**engine_params),
    YourEngine(**engine_params),
]
```

4. **Test your engine**:

```bash
python -c "from src.engine import YourEngine; print('Import OK')"
python main.py --engines
```

### Available Helper Functions

From `src.engine.base`:

```python
# De-vigging
from src.engine.base import devig_two_way, devig_three_way
p_over = devig_two_way(over_odds, under_odds)
p_home, p_draw, p_away = devig_three_way(home, draw, away)

# Lambda fitting
from src.engine.base import fit_lambda_from_ou_lines
lambda_home = fit_lambda_from_ou_lines([(0.5, 1.40, 3.10)])

# Monte Carlo simulation
from src.engine.base import simulate_1up_probabilities
p_home_1up, p_away_1up = simulate_1up_probabilities(
    lambda_home=1.5,
    lambda_away=1.2,
    n_sims=30000,
    match_minutes=95
)
```

### Required Engine Output

Your engine must return:

```python
{
    'engine': 'YourEngineName',     # string
    'lambda_home': 1.45,            # float > 0
    'lambda_away': 1.23,            # float > 0
    'lambda_total': 2.68,           # float > 0
    'p_home_1up': 0.65,             # float 0-1
    'p_away_1up': 0.55,             # float 0-1
    '1up_home_fair': 1.54,          # float >= 1.0
    '1up_away_fair': 1.82,          # float >= 1.0
    '1up_draw': 3.40,               # float >= 1.0
}
```

---

## Key Insights

### 1UP is NOT a Complementary Market

Important: **Home 1UP and Away 1UP can both happen in the same match.**

Example: Home leads 1-0 (Home 1UP hits), then Away equalizes 1-1 and goes ahead 2-1 (Away 1UP also hits).

Therefore:
- ✗ Don't use 2-way devigging on 1UP odds
- ✗ Don't normalize probabilities to sum to 1.0
- ✓ Use raw implied probabilities: `p = 1 / odds`
- ✓ Compare in probability space with MAE as primary metric

### Provider Relationships

- **Betpawa uses Sportybet's odds provider** for First Team To Score
- The FTS engine explicitly handles this (not a fallback, but correct behavior)
- This is why FTS-Calibrated-DP performs identically for Sporty and Pawa

### Performance Metrics

**Primary Metric: Probability MAE**
- Treats all outcomes fairly
- Not dominated by longshot errors

**Secondary Metric: Log-Odds MAE**
- Stable across all odds ranges
- Less intuitive but good for technical analysis

**Avoid: Odds MAE**
- Overweights longshots (error of 30 on 35→5 dominates error of 0.05 on 2→1.95)

---

## Database Schema

### Key Tables

**events** - Match records
```sql
CREATE TABLE events (
    id INTEGER PRIMARY KEY,
    sportradar_id TEXT UNIQUE,
    home_team TEXT,
    away_team TEXT,
    start_time TEXT,
    tournament_id INTEGER,
    matched INTEGER DEFAULT 0
);
```

**markets** - Unified odds (all bookmakers per row)
```sql
CREATE TABLE markets (
    id INTEGER PRIMARY KEY,
    sportradar_id TEXT,
    market_name TEXT,  -- "1X2", "Over/Under", etc.
    specifier TEXT,    -- "2.5" for O/U 2.5

    sporty_outcome_1_odds REAL,
    sporty_outcome_2_odds REAL,
    sporty_outcome_3_odds REAL,

    pawa_outcome_1_odds REAL,
    pawa_outcome_2_odds REAL,
    pawa_outcome_3_odds REAL,

    bet9ja_outcome_1_odds REAL,
    bet9ja_outcome_2_odds REAL,
    bet9ja_outcome_3_odds REAL,

    UNIQUE(sportradar_id, market_name, specifier)
);
```

**engine_calculations** - Engine results
```sql
CREATE TABLE engine_calculations (
    id INTEGER PRIMARY KEY,
    sportradar_id TEXT,
    engine_name TEXT,
    bookmaker TEXT,  -- 'sporty', 'pawa', 'bet9ja'
    lambda_home REAL,
    lambda_away REAL,
    lambda_total REAL,
    p_home_1up REAL,
    p_away_1up REAL,
    fair_home REAL,
    fair_away REAL,
    fair_draw REAL,
    actual_sporty_home REAL,
    actual_sporty_away REAL,
    actual_bet9ja_home REAL,
    actual_bet9ja_away REAL
);
```

---

## License

MIT License - See LICENSE file for details

---

## Support

For issues or questions:
- GitHub Issues: https://github.com/anthropics/claude-code/issues
- Check `/help` for CLI commands
