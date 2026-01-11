# Codebase Structure

**Analysis Date:** 2026-01-11

## Directory Layout

```
1UP_calc/
├── main.py                     # Primary CLI entry point
├── analyze_engines.py          # Engine accuracy analysis (27KB)
├── requirements.txt            # Python dependencies (no version pins)
├── LICENSE                     # Project license
├── README.md                   # Documentation
│
├── src/                        # Main source code
│   ├── __init__.py             # Package exports
│   ├── config.py               # ConfigLoader class
│   ├── run_engines.py          # Alternative engine entry point
│   ├── unified_scraper.py      # Multi-bookmaker orchestration (1028 lines)
│   │
│   ├── db/                     # Database layer
│   │   ├── __init__.py
│   │   ├── manager.py          # DatabaseManager (1479 lines, 42 methods)
│   │   └── models.py           # Event, Market dataclasses
│   │
│   ├── engine/                 # Pricing engines
│   │   ├── __init__.py
│   │   ├── base.py             # Shared utilities (14KB)
│   │   ├── poisson_calibrated.py    # CalibratedPoissonEngine (12KB)
│   │   ├── fts_calibrated_dp.py     # FTSCalibratedDPEngine (22KB)
│   │   └── runner.py           # EngineRunner orchestrator (29KB)
│   │
│   └── scraper/                # Multi-bookmaker scrapers
│       ├── __init__.py
│       ├── sporty/             # Sportybet (Playwright)
│       │   ├── __init__.py
│       │   ├── browser_manager.py   # SharedBrowserManager (7KB)
│       │   ├── events_scraper.py    # SportybetEventsScraper (10KB)
│       │   └── markets_scraper.py   # SportybetMarketsScraper (10KB)
│       ├── pawa/               # Betpawa (httpx)
│       │   ├── __init__.py
│       │   ├── config.py
│       │   ├── events_scraper.py    # BetpawaEventsScraper (8.5KB)
│       │   ├── markets_scraper.py   # BetpawaMarketsScraper (6.7KB)
│       │   └── models.py       # PawaEvent, PawaTournament (1.8KB)
│       └── bet9ja/             # Bet9ja (httpx)
│           ├── __init__.py
│           ├── config.py
│           ├── events_scraper.py    # Bet9jaEventsScraper (4.5KB)
│           ├── markets_scraper.py   # Bet9jaMarketsScraper (6.4KB)
│           └── models.py       # Bet9jaEvent (600 bytes)
│
├── config/                     # Configuration files (YAML)
│   ├── settings.yaml           # Database path, scraper settings
│   ├── engine.yaml             # Engine parameters
│   ├── markets.yaml            # Market definitions (5KB)
│   └── tournaments.yaml        # Tournament configuration (4KB)
│
├── tests/                      # Test suite
│   ├── __init__.py
│   ├── test_runner.py          # Engine recalculation harness (17KB)
│   ├── test_system.py          # Integration tests
│   ├── test_analyze.py         # Analysis tests
│   ├── test_analyze_engines.py # Engine analysis tests
│   └── test_fts_engine.py      # FTS engine unit tests
│
├── data/                       # Data storage (gitignored)
│   ├── datas.db                # SQLite database (~6.4MB)
│   └── martes_snapshots.csv    # Historical snapshots
│
├── reports/                    # Analysis output (gitignored)
│   ├── analysis_*.csv          # Engine accuracy reports
│   └── old/                    # Archive
│
└── .planning/                  # GSD planning (if exists)
    └── codebase/               # Codebase map (this directory)
```

## Directory Purposes

**src/**
- Purpose: Main application source code
- Contains: All Python modules (config, db, engine, scraper)
- Key files: `config.py`, `unified_scraper.py`, `run_engines.py`

**src/db/**
- Purpose: Database abstraction layer
- Contains: DatabaseManager, data models
- Key files:
  - `manager.py` - SQLite operations, schema management, migrations
  - `models.py` - Event, Market dataclasses

**src/engine/**
- Purpose: 1UP pricing calculation engines
- Contains: Base utilities, two production engines, orchestrator
- Key files:
  - `base.py` - Devig functions, Poisson utilities, Monte Carlo simulation
  - `poisson_calibrated.py` - Poisson-based engine with underdog correction
  - `fts_calibrated_dp.py` - FTS-anchored dynamic programming engine
  - `runner.py` - Parallel execution orchestration

**src/scraper/**
- Purpose: Multi-bookmaker scraping modules
- Contains: Three independent scraper packages
- Subdirectories:
  - `sporty/` - Sportybet scraper (Playwright browser automation)
  - `pawa/` - Betpawa scraper (httpx API client)
  - `bet9ja/` - Bet9ja scraper (httpx API client)

**config/**
- Purpose: YAML configuration files
- Contains: Settings for database, engines, markets, tournaments
- Key files:
  - `settings.yaml` - Scraper concurrency, database path
  - `engine.yaml` - Engine enable/disable, simulation parameters
  - `markets.yaml` - Market ID mappings between bookmakers
  - `tournaments.yaml` - Tournament definitions

**tests/**
- Purpose: Test suite
- Contains: Integration and unit tests
- Key files:
  - `test_system.py` - Integration tests (imports, DB, engines)
  - `test_fts_engine.py` - FTS engine unit tests
  - `test_runner.py` - Engine runner tests

**data/**
- Purpose: Runtime data storage (gitignored)
- Contains: SQLite database, CSV snapshots
- Key files: `datas.db` (SQLite database)

**reports/**
- Purpose: Analysis output (gitignored)
- Contains: CSV reports from `analyze_engines.py`

## Key File Locations

**Entry Points:**
- `main.py` - Primary CLI for full pipeline
- `src/run_engines.py` - Engines-only execution
- `analyze_engines.py` - Analysis and reporting

**Configuration:**
- `config/settings.yaml` - Scraper and database settings
- `config/engine.yaml` - Engine configuration
- `config/markets.yaml` - Market mappings
- `config/tournaments.yaml` - Tournament definitions
- `requirements.txt` - Python dependencies

**Core Logic:**
- `src/config.py` - Configuration loader
- `src/unified_scraper.py` - Multi-bookmaker orchestration
- `src/db/manager.py` - Database operations
- `src/engine/runner.py` - Engine execution orchestrator

**Testing:**
- `tests/test_system.py` - System integration tests
- `tests/test_fts_engine.py` - Engine unit tests

**Documentation:**
- `README.md` - User-facing documentation
- `LICENSE` - Project license

## Naming Conventions

**Files:**
- snake_case for all Python files: `unified_scraper.py`, `events_scraper.py`, `poisson_calibrated.py`
- Test files: `test_*.py` pattern
- YAML configs: lowercase with underscores

**Directories:**
- snake_case for package directories: `src/`, `src/db/`, `src/engine/`, `src/scraper/`
- Bookmaker names: `sporty/`, `pawa/`, `bet9ja/`

**Special Patterns:**
- `__init__.py` for package exports
- No `index.py` or barrel exports (Python convention)

## Where to Add New Code

**New Scraper/Bookmaker:**
- Primary code: `src/scraper/{bookmaker_name}/`
- Create: `__init__.py`, `config.py`, `events_scraper.py`, `markets_scraper.py`, `models.py`
- Integration: Update `src/unified_scraper.py` to orchestrate new scraper

**New Pricing Engine:**
- Implementation: `src/engine/{algorithm}_engine.py`
- Inherit from: `BaseEngine` in `src/engine/base.py`
- Registration: Update `src/engine/__init__.py` and `src/engine/runner.py`

**New Configuration:**
- Add YAML file: `config/{name}.yaml`
- Loader method: Add to `src/config.py:ConfigLoader`

**Utilities:**
- Shared helpers: Add to appropriate module or create `src/utils/` if needed
- Database utilities: `src/db/manager.py` methods
- Engine utilities: `src/engine/base.py` functions

## Special Directories

**data/**
- Purpose: Runtime data (database, snapshots)
- Source: Generated at runtime
- Committed: No (in `.gitignore`)

**reports/**
- Purpose: Analysis output
- Source: Generated by `analyze_engines.py`
- Committed: No (in `.gitignore`)

**.venv/**
- Purpose: Python virtual environment
- Source: Created by `python -m venv .venv`
- Committed: No (in `.gitignore`)

---

*Structure analysis: 2026-01-11*
*Update when directory structure changes*
