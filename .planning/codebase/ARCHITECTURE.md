# Architecture

**Analysis Date:** 2026-01-11

## Pattern Overview

**Overall:** Layered Monolith with Multi-Bookmaker Scraping Pipeline

**Key Characteristics:**
- CLI-driven workflow with distinct scrape → calculate → analyze phases
- Multi-bookmaker aggregation (Sportybet, Betpawa, Bet9ja)
- Event matching via Sportradar IDs
- Pluggable pricing engines for 1UP probability calculation
- SQLite database as central data store

## Layers

**CLI/Orchestration Layer:**
- Purpose: Entry points and workflow coordination
- Contains: Command-line interfaces, workflow orchestration
- Entry points: `main.py` (full pipeline), `src/run_engines.py` (engines only), `analyze_engines.py` (analysis)
- Depends on: Scraper layer, Engine layer, Database layer
- Used by: End users via command line

**Scraper Layer:**
- Purpose: Multi-bookmaker odds aggregation
- Contains: Three independent scraper modules (Sporty, Pawa, Bet9ja)
- Locations:
  - `src/scraper/sporty/` - Playwright-based browser automation
  - `src/scraper/pawa/` - HTTP API client (httpx)
  - `src/scraper/bet9ja/` - HTTP API client (httpx)
  - `src/unified_scraper.py` - Orchestration and event matching
- Depends on: Database layer, Configuration layer
- Used by: CLI orchestration layer

**Engine Layer:**
- Purpose: 1UP pricing calculation
- Contains: Monte Carlo simulation engines with calibration
- Locations:
  - `src/engine/base.py` - Shared utilities (devig, Poisson functions, simulation)
  - `src/engine/poisson_calibrated.py` - Poisson with underdog correction
  - `src/engine/fts_calibrated_dp.py` - FTS-anchored dynamic programming
  - `src/engine/runner.py` - Engine execution orchestrator (ThreadPool)
- Depends on: Database layer, numpy for vectorized computation
- Used by: CLI orchestration layer

**Database Layer:**
- Purpose: Persistent storage and retrieval
- Contains: DatabaseManager class with schema management
- Location: `src/db/manager.py`, `src/db/models.py`
- Tables: tournaments, events, markets, market_snapshots, scraping_history, engine_calculations
- Depends on: sqlite3 (built-in)
- Used by: All layers

**Configuration Layer:**
- Purpose: YAML-based configuration management
- Contains: ConfigLoader class
- Location: `src/config.py`
- Config files: `config/settings.yaml`, `config/engine.yaml`, `config/markets.yaml`, `config/tournaments.yaml`
- Depends on: pyyaml
- Used by: All layers

## Data Flow

**Scraping Workflow:**

1. User runs: `python main.py --scrape`
2. UnifiedScraper.run() initializes
3. For each enabled tournament:
   - Fetch events from all three bookmakers in parallel
   - Match events by Sportradar ID
   - Fetch markets for matched events
   - Normalize and store odds in database
   - Create market snapshot for versioning
4. Results stored in `markets` and `market_snapshots` tables

**Engine Workflow:**

1. User runs: `python main.py --engines` (or automatic after scrape)
2. EngineRunner.run_new_snapshots() loads unprocessed sessions
3. For each session:
   - For each engine (Poisson-Calibrated, FTS-Calibrated-DP):
     - For each bookmaker (sporty, pawa, bet9ja):
       - Extract required markets (1X2, O/U, FTS, BTTS)
       - Fit Poisson lambdas from market odds
       - Calculate 1UP probabilities via simulation or DP
       - Apply margins to get fair odds
       - Store results in `engine_calculations` table
4. Parallel processing via ThreadPoolExecutor (CPU count workers)

**Analysis Workflow:**

1. User runs: `python analyze_engines.py`
2. Load engine_calculations from database
3. Compare calculated fair odds against actual bookmaker odds
4. Calculate error metrics (MAE, probability errors)
5. Export results to CSV in `reports/` directory

**State Management:**
- Stateless request processing (each run is independent)
- All state persisted in SQLite database
- Scraping sessions tracked in `scraping_history` table

## Key Abstractions

**BaseEngine:**
- Purpose: Abstract base class for pricing engines
- Examples: `src/engine/poisson_calibrated.py:CalibratedPoissonEngine`, `src/engine/fts_calibrated_dp.py:FTSCalibratedDPEngine`
- Pattern: Template method pattern - subclasses implement `calculate(markets, bookmaker)`

**DatabaseManager:**
- Purpose: Single source of truth for database operations
- Example: `src/db/manager.py`
- Pattern: Facade pattern - centralizes all SQLite interactions

**Scraper Modules:**
- Purpose: Isolated per-bookmaker data extraction
- Examples: SportybetEventsScraper, BetpawaEventsScraper, Bet9jaEventsScraper
- Pattern: Strategy pattern - interchangeable scrapers with common interface

**ConfigLoader:**
- Purpose: Centralized configuration access
- Example: `src/config.py`
- Pattern: Singleton-like (imported as module, not instantiated multiple times)

**UnifiedScraper:**
- Purpose: Multi-bookmaker orchestration and event matching
- Example: `src/unified_scraper.py`
- Pattern: Facade pattern - coordinates multiple scrapers

## Entry Points

**Primary CLI:**
- Location: `main.py`
- Triggers: User runs `python main.py` with optional flags
- Responsibilities: Parse CLI args, orchestrate scrape/engine workflow

**Engine Runner:**
- Location: `src/run_engines.py`
- Triggers: User runs `python src/run_engines.py`
- Responsibilities: Execute engines on existing database without scraping

**Analysis Script:**
- Location: `analyze_engines.py`
- Triggers: User runs `python analyze_engines.py`
- Responsibilities: Generate accuracy reports from engine calculations

## Error Handling

**Strategy:** Exception bubbling to top-level handler with logging

**Patterns:**
- Try/catch at orchestration boundaries (scraper tasks, engine calculations)
- Async errors: `asyncio.gather(..., return_exceptions=True)` with error logging
- Database errors: Logged and re-raised
- Scraper errors: Continue processing other events (partial failure tolerance)

## Cross-Cutting Concerns

**Logging:**
- Python logging module with per-module loggers
- Format: `logger = logging.getLogger(__name__)`
- Output: Console (stdout/stderr)
- Levels: DEBUG, INFO, WARNING, ERROR

**Validation:**
- Market data validation during normalization
- Odds range checking (implicit - missing explicit validation)
- Configuration validation: Minimal (YAML parsing errors raise exceptions)

**Concurrency:**
- Async/await for I/O-bound scraping operations
- ThreadPoolExecutor for CPU-bound engine calculations
- Semaphores for rate limiting API requests
- asyncio.Semaphore per bookmaker (default 10 concurrent requests)

---

*Architecture analysis: 2026-01-11*
*Update when major patterns change*
