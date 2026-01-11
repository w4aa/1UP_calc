# Coding Conventions

**Analysis Date:** 2026-01-11

## Naming Patterns

**Files:**
- snake_case for all Python files
- Examples: `unified_scraper.py`, `events_scraper.py`, `poisson_calibrated.py`, `fts_calibrated_dp.py`
- Test files: `test_*.py` pattern (e.g., `test_system.py`, `test_fts_engine.py`)

**Functions:**
- snake_case for all functions
- Action-oriented names: `get_db_path()`, `load_settings()`, `upsert_market()`, `devig_two_way()`
- Async functions: No special prefix (standard async/await pattern)

**Variables:**
- snake_case for all variables
- Descriptive names: `sportradar_id`, `market_name`, `lambda_home`, `lambda_away`
- Abbreviations: `db`, `config`, `logger`, `cursor`
- Bookmaker prefixes: `sporty_`, `pawa_`, `bet9ja_`

**Types:**
- PascalCase for classes: `ConfigLoader`, `DatabaseManager`, `CalibratedPoissonEngine`
- PascalCase for dataclasses: `Event`, `Market`, `SportyEvent`, `PawaEvent`
- Type hints used throughout: `list[dict]`, `Optional[str]`, `Tuple[float, bool, bool]`

## Code Style

**Formatting:**
- 4 spaces per indentation level (Python standard)
- No line length limit enforced (found lines up to 270+ characters in SQL)
- Double quotes (`"`) preferred for strings
- No semicolons (Python standard)

**Linting:**
- No formal linting configuration detected
- No `.pylintrc`, `.flake8`, or `ruff.toml`
- Manual code review discipline

## Import Organization

**Order:**
1. Standard library imports: `asyncio`, `sys`, `pathlib`, `logging`
2. Third-party imports: `yaml`, `numpy`, `playwright`, `httpx`
3. Local imports: `from src.config import ConfigLoader`

**Grouping:**
- Blank line between groups
- No explicit sorting within groups
- Type imports: `from typing import Optional, Tuple`

**Path Aliases:**
- None (uses relative and absolute imports)
- Project root added to sys.path when needed

## Error Handling

**Patterns:**
- Throw exceptions, catch at boundaries (main functions, orchestrators)
- Async: `asyncio.gather(..., return_exceptions=True)` with error logging
- Database: Exceptions logged and re-raised or swallowed with debug logging

**Error Types:**
- Bare `except Exception:` used frequently (14+ instances)
- Example: `src/db/manager.py:309, 851-863` - Exception swallowing during migrations and odds conversion
- Missing specific exception handling (ValueError, TypeError, KeyError)

**Logging:**
- Errors logged before re-raising: `logger.error(f"Error: {e}")`
- Some exceptions silently caught without logging (anti-pattern)

## Logging

**Framework:**
- Python built-in logging module
- Per-module loggers: `logger = logging.getLogger(__name__)`

**Patterns:**
- Structured logging with f-strings: `logger.info(f"[Pawa] Fetching: {event.home_team} vs {event.away_team}")`
- Levels: DEBUG, INFO, WARNING, ERROR
- Output: Console only (stdout/stderr)

## Comments

**When to Comment:**
- Module docstrings: Triple-quoted strings at top of file explaining purpose
- Class docstrings: Immediately after class definition
- Method docstrings: Args, Returns, description
- Section headers: `# ==========================================` for logical sections

**JSDoc/TSDoc:**
- Not applicable (Python)

**TODO Comments:**
- No standard format detected
- Limited TODO usage in codebase

## Function Design

**Size:**
- No enforced limit (some functions exceed 200 lines)
- Example: `src/unified_scraper.py:_map_bet9ja_market` (90+ lines)

**Parameters:**
- No max parameter limit
- Type hints used: `def upsert_market(self, sportradar_id: str, market_name: str, ...) -> None:`
- Dataclasses preferred for complex parameter groups

**Return Values:**
- Explicit returns with type hints
- Optional returns: `-> Optional[dict]`
- Early returns for guard clauses

## Module Design

**Exports:**
- Named exports via `__all__` in `__init__.py`
- Example: `src/engine/__init__.py` exports `CalibratedPoissonEngine`, `FTSCalibratedDPEngine`
- No default exports (Python convention)

**Barrel Files:**
- `__init__.py` re-exports public API
- Example: `src/scraper/sporty/__init__.py` exports scrapers and models
- Private modules (prefixed with `_`) not exported

---

*Convention analysis: 2026-01-11*
*Update when patterns change*
