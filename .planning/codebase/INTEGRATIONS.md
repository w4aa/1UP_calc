# External Integrations

**Analysis Date:** 2026-01-11

## APIs & External Services

**Payment Processing:**
- Not applicable

**Email/SMS:**
- Not applicable

**External APIs:**

1. **Sportybet API** - First-to-score probability calculation data source
   - Base URL: `https://www.sportybet.com`
   - Endpoint: `/api/ng/factsCenter/pcEvents`
   - Integration: Browser automation via Playwright (headless)
   - Auth: None (public API with anti-bot measures)
   - Files: `src/scraper/sporty/events_scraper.py`, `src/scraper/sporty/markets_scraper.py`
   - Network interception to capture API responses
   - Markets: 1X2, 1UP, 2UP, Over/Under, BTTS, First Team to Score

2. **Betpawa API** - Betting odds aggregation
   - Base URL: `https://www.betpawa.com.gh`
   - Endpoints:
     - `/api/sportsbook/v3/events/lists/by-queries` - Event lists
     - `/api/sportsbook/v3/events` - Event details
   - Integration: Direct HTTP API calls via httpx AsyncClient
   - Auth: None
   - Custom Headers: `x-pawa-brand: betpawa-ghana`, `devicetype: web`
   - Files: `src/scraper/pawa/config.py`, `src/scraper/pawa/events_scraper.py`, `src/scraper/pawa/markets_scraper.py`
   - Markets: 1X2, Over/Under, Asian Handicap, BTTS

3. **Bet9ja API** - Third bookmaker odds source
   - Base URL: `https://sports.bet9ja.com`
   - Endpoints:
     - `/desktop/feapi/PalimpsestAjax/GetEventsInGroupV2` - Events in tournament
     - `/desktop/feapi/PalimpsestAjax/GetEvent` - Event details
   - Integration: HTTP API via httpx
   - Auth: None
   - Cache Version: `1.301.2.219` (configurable)
   - Files: `src/scraper/bet9ja/config.py`, `src/scraper/bet9ja/events_scraper.py`, `src/scraper/bet9ja/markets_scraper.py`
   - Markets: 1X2, 1UP, 2UP, Over/Under, Asian Handicap, BTTS, Home/Away O/U

**Event Matching:**
- Sportradar IDs (`sr:match:XXXXX`) used as primary key across all bookmakers
- Enables cross-bookmaker event correlation

## Data Storage

**Databases:**
- SQLite - Local database for events, markets, calculations
  - Connection: `data/datas.db` (relative path)
  - Client: Python built-in sqlite3 module
  - Migrations: Managed in `src/db/manager.py:_run_migrations()`
  - Tables: tournaments, events, markets, market_snapshots, scraping_history, engine_calculations

**File Storage:**
- CSV Reports - Analysis output saved to `reports/` directory
  - Engine accuracy statistics
  - Value bet identification
  - Per-bookmaker analysis

**Caching:**
- None (no Redis or external cache)

## Authentication & Identity

**Auth Provider:**
- Not applicable (no user authentication)

**OAuth Integrations:**
- None

## Monitoring & Observability

**Error Tracking:**
- None (no Sentry or external error tracking)
- Python logging to console only

**Analytics:**
- None

**Logs:**
- Python logging module to stdout/stderr
  - Configured per module: `logger = logging.getLogger(__name__)`
  - Console output only (no log aggregation service)

## CI/CD & Deployment

**Hosting:**
- Local command-line application (no hosted deployment)
  - Execution: `python main.py`

**CI Pipeline:**
- None detected

## Environment Configuration

**Development:**
- Required config files: `config/settings.yaml`, `config/engine.yaml`, `config/markets.yaml`, `config/tournaments.yaml`
- Database: `data/datas.db` (created automatically if missing)
- No environment variables required

**Staging:**
- Not applicable (local CLI tool)

**Production:**
- Same as development (no separate production environment)

## Webhooks & Callbacks

**Incoming:**
- None

**Outgoing:**
- None

---

*Integration audit: 2026-01-11*
*Update when adding/removing external services*
