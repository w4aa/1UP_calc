# Codebase Concerns

**Analysis Date:** 2026-01-11

## Tech Debt

**God Objects - Monolithic Classes:**
- Issue: DatabaseManager (`src/db/manager.py`) is 1479 lines with 42 methods handling all database operations
- Why: Database logic centralized without further decomposition
- Impact: Difficult to test, understand, and maintain; high cognitive load
- Fix approach: Split into specialized managers (EventsManager, MarketsManager, EngineCalculationsManager)

**Large Functions - Complex Market Mapping:**
- Issue: `_map_bet9ja_market()` in `src/unified_scraper.py:859-950` is 90+ lines with nested conditionals
- Why: Bet9ja market naming differs significantly from Sporty/Pawa
- Impact: Hard to understand logic flow, easy to introduce bugs
- Fix approach: Extract outcome normalization to separate functions, use strategy pattern for market type handling

**Repeated Code - Odds Conversion:**
- Issue: Pattern `try: float(value) except Exception: None` repeated 10+ times in `src/db/manager.py:851-863`
- Why: No shared utility function for safe numeric conversion
- Impact: Code duplication, inconsistent error handling
- Fix approach: Create `safe_float()` utility in `src/db/manager.py` or `src/utils.py`

## Known Bugs

**Race Condition - Async Counter Updates:**
- Symptoms: Scraping statistics (saved_total) may be inaccurate under high concurrency
- Trigger: Multiple async tasks updating `nonlocal saved_total` without synchronization
- Files: `src/unified_scraper.py:544, 691` - nonlocal variables in async closures
- Workaround: Currently low impact due to logging-only usage
- Root cause: No lock protection for shared state in async context
- Fix: Use asyncio.Lock or atomic counter for nonlocal variables

**Silent Failures - Bet9ja Mapping:**
- Symptoms: Bet9ja markets silently unmapped without user notification
- Trigger: Exception in `_map_bet9ja_market()` caught and ignored
- Files: `src/unified_scraper.py:240` - bare `except Exception:` swallows errors
- Workaround: Manual database inspection to find missing markets
- Root cause: Exception swallowing without logging
- Fix: Add error logging with context (event details, market name)

## Security Considerations

**SQL Injection Risk in DDL:**
- Risk: F-strings used directly in ALTER TABLE statements could allow injection if column names are user-controlled
- Files: `src/db/manager.py:340, 368, 390, 401` - `ALTER TABLE {table_name} ADD COLUMN {col_name} {col_type}`
- Current mitigation: None (column names hardcoded but pattern is dangerous)
- Recommendations: Use parameterized DDL or whitelist column names explicitly

**Missing Input Validation:**
- Risk: No validation of sportradar_id, market_name, or specifier parameters before database operations
- Files: `src/db/manager.py` - upsert methods accept arbitrary string inputs
- Current mitigation: None
- Recommendations: Add input validation for IDs (format checking), market names (whitelist), specifiers (regex validation)

## Performance Bottlenecks

**N+1 Query Pattern:**
- Problem: Engine runner loads all events, then fetches market snapshots one-by-one
- Files: `src/engine/runner.py:245-260` - sequential market snapshot retrieval per event
- Measurement: Not measured (qualitative observation)
- Cause: Individual SELECT queries instead of batch fetch
- Improvement path: Add `get_market_snapshots_batch(sportradar_ids)` to fetch all snapshots in single query

**Large Memory Allocation:**
- Problem: Monte Carlo simulation creates large numpy arrays for all simulations at once
- Files: `src/engine/base.py:232-245` - `numpy.random.poisson()` with shape (n_sims, max_goals)
- Measurement: Not measured (default n_sims=50000 × max_goals could be GBs)
- Cause: Vectorized approach trades memory for speed
- Improvement path: Batch simulations into chunks if memory becomes an issue

## Fragile Areas

**Exception Handling - Bare Catches:**
- Why fragile: 14+ instances of bare `except Exception:` mask specific errors
- Files:
  - `src/db/manager.py:309` - Migration index creation
  - `src/db/manager.py:851-863` - Odds conversion (6 instances)
  - `src/engine/base.py:3` - scipy.optimize import
  - `src/engine/poisson_calibrated.py:246` - Lambda fitting
  - `src/unified_scraper.py:240, 899` - Market mapping
  - `src/scraper/bet9ja/events_scraper.py:102` - Event parsing
  - `src/scraper/bet9ja/markets_scraper.py:166` - Outcomes parsing
- Common failures: Production debugging extremely difficult; silent failures
- Safe modification: Replace with specific exception types (ValueError, KeyError, TypeError) and log context
- Test coverage: No tests for exception paths

**Database Connection Management:**
- Why fragile: Connection opened in `__init__` but only closed in `run()` finally block
- Files: `src/unified_scraper.py:166` - `self.db.connect()` in constructor
- Common failures: Connection leaks if exception occurs outside `run()` method
- Safe modification: Use context managers (`with db`) or ensure cleanup in `__del__`
- Test coverage: No connection lifecycle tests

## Scaling Limits

**SQLite Concurrency:**
- Current capacity: Single-writer limitation (SQLite design)
- Limit: ~100 concurrent writes before lock contention
- Symptoms at limit: "database is locked" errors, write timeouts
- Scaling path: Migrate to PostgreSQL for multi-writer support

**Single-Threaded Scraping:**
- Current capacity: Limited by Python GIL and single event loop
- Limit: ~50-100 events/minute depending on bookmaker response time
- Symptoms at limit: Scraping takes hours for large tournaments
- Scaling path: Multi-process scraping with process pool

## Dependencies at Risk

**Unpinned Requirements:**
- Risk: `requirements.txt` has no version pins - breaking changes in dependencies could break app
- Files: `requirements.txt` - all packages listed without versions (numpy, pyyaml, playwright, httpx)
- Impact: Non-reproducible builds, potential runtime failures after dependency updates
- Migration plan: Pin all dependencies with `pip freeze > requirements.txt`

**Optional scipy:**
- Risk: scipy is commented out but engine code falls back to grid search if unavailable
- Files: `requirements.txt:7` (commented), `src/engine/base.py:3` (optional import)
- Impact: Slower lambda fitting without scipy, reduced accuracy
- Migration plan: Make scipy required or document performance impact

## Missing Critical Features

**No Retry Mechanism for API Failures:**
- Problem: HTTP requests fail permanently on transient errors (network timeout, rate limit)
- Current workaround: Manual re-run of scraping
- Blocks: Automated scraping pipelines, scheduled jobs
- Implementation complexity: Medium (add retry decorator with exponential backoff)

**No Configuration Validation:**
- Problem: YAML config files not validated on load - missing keys cause runtime errors
- Current workaround: Manual YAML editing and trial-and-error
- Blocks: Easy configuration changes, deployment automation
- Implementation complexity: Low (add schema validation with pyyaml or pydantic)

## Test Coverage Gaps

**No Database Operation Tests:**
- What's not tested: All DatabaseManager methods (upsert, get, insert operations)
- Files: `src/db/manager.py` - 1479 lines, 0 unit tests
- Risk: Schema migrations could break existing data, queries could return wrong results
- Priority: High
- Difficulty to test: Medium (need test database setup/teardown)

**No Scraper Unit Tests:**
- What's not tested: Individual scraper modules (SportybetEventsScraper, BetpawaEventsScraper, Bet9jaEventsScraper)
- Files: `src/scraper/sporty/`, `src/scraper/pawa/`, `src/scraper/bet9ja/` - no corresponding test files
- Risk: API changes break scrapers silently, market mapping logic untested
- Priority: High
- Difficulty to test: Medium (need mock HTTP responses or VCR cassettes)

**No Engine Edge Case Tests:**
- What's not tested: Zero goals, extreme lambdas, invalid odds, missing markets
- Files: `src/engine/poisson_calibrated.py`, `src/engine/fts_calibrated_dp.py` - limited test coverage
- Risk: Edge cases cause NaN, Inf, or incorrect probabilities
- Priority: Medium
- Difficulty to test: Low (synthetic market data)

---

*Concerns audit: 2026-01-11*
*Update as issues are fixed or new ones discovered*
