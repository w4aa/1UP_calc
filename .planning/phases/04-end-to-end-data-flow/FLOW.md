# End-to-End Data Flow

## Overview

The 1UP Calculator pipeline transforms tournament configurations into calibrated 1UP odds through a five-stage data flow: tournament sync → change detection → multi-bookmaker scraping → snapshot creation → engine execution. The pipeline is optimized for efficiency with change detection and duplicate prevention.

## Pipeline Stages

### Stage 1: Tournament Configuration

**Source**: [config/tournaments.yaml](../../../config/tournaments.yaml)

**Process**: UnifiedScraper syncs enabled tournaments to database during `_process_tournament()` ([src/unified_scraper.py:356-367](../../../src/unified_scraper.py#L356-L367))

**Output**: Tournament records in `tournaments` table

Each tournament contains:
- Tournament ID, name, sport
- Category IDs for Sportybet and BetPawa
- Competition ID for BetPawa
- Enabled status

### Stage 2: BetPawa Change Detection

**Trigger**: For each enabled tournament

**Process**: `_check_betpawa_changes_for_tournament()` ([src/unified_scraper.py:369](../../../src/unified_scraper.py#L369))

1. Fetch BetPawa events and 1x2 odds
2. Compare current odds against latest `market_snapshots` entry
3. Identify events with changed 1x2 odds (by sportradar_id)
4. Update cached 1x2 odds in database

**Early Return**: If no 1x2 changes detected and `force=False`, skip tournament entirely

**Output**: Set of changed `sportradar_id` values

### Stage 3: Multi-Bookmaker Scraping

**Condition**: Only executes if Stage 2 detected changes

**Process**: Parallel scraping of three bookmakers ([src/unified_scraper.py:406-489](../../../src/unified_scraper.py#L406-L489))

1. **Sportybet**: Events + Markets (shared browser, filtered by changed IDs)
2. **BetPawa**: Events + Markets (HTTP client, filtered by changed IDs)
3. **Bet9ja**: Events + Markets (HTTP client, filtered by changed IDs)

**Event Filtering**: Only scrape events with sportradar_id in changed set

**Scraper Isolation**: Uses `asyncio.gather(..., return_exceptions=True)` - failure of one scraper doesn't block others

**Output**:
- Events stored in `events` table
- Markets stored in `markets` table (one row per bookmaker per market)

### Stage 4: Snapshot Creation

**Trigger**: After all bookmaker scrapers complete for a tournament

**Process**: `create_snapshots_for_matched_events()` ([src/db/manager.py](../../../src/db/manager.py))

1. Query matched events (events present in both Sportybet and BetPawa)
2. For each matched event:
   - Create `scraping_history` record (one per match)
   - Create `market_snapshots` entries (one per market, linked to history_id)

**Schema**:
- `scraping_history`: Tracks when each match was scraped
- `market_snapshots`: Point-in-time odds from all bookmakers

**Output**: New scraping_history_id values flagged as unprocessed

### Stage 5: Engine Execution

**Trigger**: Automatic via `runner.run_new_snapshots()` ([src/unified_scraper.py:209](../../../src/unified_scraper.py#L209))

**Process**: EngineRunner processes unprocessed sessions ([src/engine/runner.py](../../../src/engine/runner.py))

1. Query `get_unprocessed_sessions()` - scraping_history entries without calculations
2. For each unprocessed session:
   - Load market snapshots for that scraping_history_id
   - Run FTS-Calibrated-DP engine
   - Calculate 1UP fair odds from 1x2 base odds
3. Store results in `engine_calculations` table
4. Mark session as processed

**Duplicate Prevention**: Unique constraint on `(sportradar_id, scraping_history_id)` prevents re-calculating same snapshot

**Parallel Execution**: Uses ThreadPoolExecutor (default: CPU count workers)

**Output**: `engine_calculations` records containing:
- Calculated 1UP odds (home_win_1up, away_win_1up, draw_1up)
- Actual 1UP odds from each bookmaker
- MAE (Mean Absolute Error) vs each bookmaker

## Error Handling

### Scraper Failures

**Pattern**: Isolated per bookmaker via `gather(..., return_exceptions=True)`

**Behavior**:
- If Sportybet fails: BetPawa and Bet9ja continue
- If BetPawa fails: Sportybet and Bet9ja continue
- Errors logged but don't propagate

### Database Errors

**Pattern**: Logged and bubbled to top-level

**Behavior**: Database connection/query failures stop pipeline

### Partial Success

**Support**: Yes - pipeline continues if individual scrapers fail

**Example**: Sportybet times out → BetPawa and Bet9ja data still collected → snapshots created → engines run

## Performance Characteristics

### Concurrency Controls

- **Tournament Processing**: Semaphore-limited parallel execution (configurable via `max_tournaments_concurrent`)
- **Sportybet Markets**: Shared browser with page pool (configurable via `max_sporty_concurrent`)
- **Engine Execution**: ThreadPoolExecutor (default: CPU count workers)

### Optimization Techniques

1. **Change Detection**: Skip tournaments with no 1x2 changes (avoids unnecessary API calls)
2. **Event Filtering**: Only scrape events with detected changes (reduces data transfer)
3. **Shared Browser**: Single Playwright instance for all Sportybet tournaments (connection pooling)
4. **Duplicate Prevention**: Snapshot-aware engine execution (unique constraint prevents recalculation)

### Typical Performance

- **Full Run** (8 tournaments, ~200 events): 2-5 minutes
- **Incremental Run** (no changes): < 30 seconds
- **Engine Execution**: ~5-10 seconds per tournament

## Entry Points

### Full Pipeline

```bash
python main.py
```

Runs: Scrape → Engines → Results

### Scrape Only

```bash
python main.py --scrape
```

Skips engine execution (useful for data collection without calculation)

### Engines Only

```bash
python main.py --engines
```

Processes any unprocessed snapshots without new scraping

### Force Mode

```bash
python main.py --force
```

Bypasses change detection, scrapes all enabled tournaments regardless of odds changes

### Analysis Mode

```bash
python main.py --analyze
```

Runs full pipeline + displays engine accuracy summary

## Key Integration Points

1. **Config → Database**: Tournament sync in `_process_tournament()` ([src/unified_scraper.py:356-367](../../../src/unified_scraper.py#L356-L367))
2. **Change Detection → Scraping**: `_check_betpawa_changes_for_tournament()` returns changed IDs ([src/unified_scraper.py:369](../../../src/unified_scraper.py#L369))
3. **Scraping → Snapshots**: `create_snapshots_for_matched_events()` triggered after scrapers complete ([src/unified_scraper.py:535](../../../src/unified_scraper.py#L535))
4. **Snapshots → Engines**: `runner.run_new_snapshots()` automatically processes new snapshots ([src/unified_scraper.py:209](../../../src/unified_scraper.py#L209))
5. **Results → Storage**: Engine results written to `engine_calculations` table ([src/engine/runner.py](../../../src/engine/runner.py))
