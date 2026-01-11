# Technology Stack

**Analysis Date:** 2026-01-11

## Languages

**Primary:**
- Python 3.9+ - All application code (`src/**/*.py`)
  - Type hints used throughout (list[dict], Optional, Tuple)
  - Async/await patterns with asyncio

## Runtime

**Environment:**
- Python 3.9+ (via `.venv/`)
- asyncio for concurrent scraping operations

**Package Manager:**
- pip - Standard Python package manager
- Lockfile: None (basic `requirements.txt` without version pinning)

## Frameworks

**Core:**
- None (pure Python async CLI application)

**Testing:**
- Python built-in testing approach (test_*.py functions with manual assertions)
- No pytest or unittest framework

**Build/Dev:**
- No build tools (pure Python execution)

## Key Dependencies

**Critical:**
- numpy (latest) - Vectorized Monte Carlo simulations, Poisson sampling - `src/engine/base.py`, `src/engine/poisson_calibrated.py`
- playwright (latest) - Browser automation for Sportybet scraping - `src/scraper/sporty/browser_manager.py`
- httpx (latest) - Async HTTP client for Betpawa/Bet9ja APIs - `src/scraper/pawa/`, `src/scraper/bet9ja/`
- pyyaml (latest) - YAML configuration loading - `src/config.py`

**Infrastructure:**
- sqlite3 (built-in) - Database for events, markets, calculations - `src/db/manager.py`
- scipy (optional) - Lambda optimization via L-BFGS-B - `src/engine/base.py` (fallback to grid search if unavailable)

## Configuration

**Environment:**
- YAML-based configuration (no `.env` files)
- Config files: `config/settings.yaml`, `config/engine.yaml`, `config/markets.yaml`, `config/tournaments.yaml`
- Database path: `data/datas.db` (relative to project root)

**Build:**
- No build configuration (interpreted Python)

## Platform Requirements

**Development:**
- Windows/Linux/macOS (any platform with Python 3.9+)
- Virtual environment recommended (`.venv/`)
- Playwright browser installation required (`playwright install`)

**Production:**
- Command-line application (no server deployment)
- Runs on user's Python installation
- Database: SQLite (local file)

---

*Stack analysis: 2026-01-11*
*Update after major dependency changes*
