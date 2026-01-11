# 1UP Calculation Prototype

## What This Is

A prototype system for calculating 1x2 1UP market odds for BetPawa by scraping competitor odds (Sportybet, Bet9ja), tracking odds changes in a database, and running the FTS_CALIBRATED_DP-PY engine to calculate BetPawa's 1UP odds for comparison. The goal is to validate the calculation model and demonstrate its performance to stakeholders and developers for production implementation.

## Core Value

Accurate 1UP calculation that consistently produces competitive odds compared to Sportybet and Bet9ja, validated by tracking engine performance across all odds changes.

## Requirements

### Validated

- ✓ Multi-bookmaker scraping (Sportybet, BetPawa, Bet9ja) - existing
- ✓ FTS_CALIBRATED_DP-PY engine for 1UP calculation - existing
- ✓ SQLite database storage (tournaments, events, markets, market_snapshots, engine_calculations) - existing
- ✓ Event matching via Sportradar IDs - existing
- ✓ CLI-driven manual execution workflow - existing
- ✓ YAML-based configuration system - existing
- ✓ Market snapshot versioning for odds change tracking - existing

### Active

- [ ] Change-based scraping: Only scrape when BetPawa 1x2 odds change from last market_snapshot
- [ ] Automatic engine execution: Run FTS_CALIBRATED_DP-PY for every new market_snapshot created
- [ ] Complete data flow: Tournament → Events → Check existing markets → Compare 1x2 odds → Scrape if changed → Calculate 1UP → Store results
- [ ] Data quality validation: Ensure scrapers work smoothly without errors
- [ ] Clear, understandable codebase: Ready to share with stakeholders and developers
- [ ] Performance tracking: Store all calculations for analysis and engine refinement

### Out of Scope

- UI/dashboard - Stakeholders will analyze data directly from database or exports
- Changes to FTS_CALIBRATED_DP-PY engine logic - Engine is proven, only use it as-is
- Automated scheduling/cron jobs - Keep manual execution for controlled periodic runs throughout the day
- Real-time scraping - Runs manually when trader triggers it, not continuously
- Production deployment infrastructure - This is a prototype for handing off to dev team

## Context

**Business Context:**
- BetPawa is launching a new 1x2 1UP market that pays out whenever a team leads by 1 goal (both 1 and 2 outcomes) and at final match outcome
- Sportybet and Bet9ja already offer this market - they are the competitive benchmark
- Trader runs this tool periodically throughout the day to monitor how BetPawa's calculated odds compare to competitors as markets move
- Results will be shared with stakeholders to approve the pricing model and with developers to implement production system

**Technical Context:**
- Existing codebase has scraping infrastructure for all 3 bookmakers (Playwright for Sportybet, httpx for BetPawa/Bet9ja)
- FTS_CALIBRATED_DP-PY engine provides accurate 1UP calculations using dynamic programming with FTS anchoring
- Database schema supports market snapshots for versioning odds changes over time
- Python 3.9+ async architecture with numpy for vectorized calculations

**Workflow:**
- Trader manually runs script for selected tournaments
- For each event: Check if it exists in DB with market data
- If exists: Compare new BetPawa 1x2 odds against last market_snapshot
- If 1x2 changed: Scrape all bookmakers and create new market_snapshot
- If unchanged: Skip event
- Engine automatically calculates 1UP for all new snapshots
- Results accumulate in DB for performance analysis

**Purpose:**
- Validate that FTS_CALIBRATED_DP-PY produces competitive 1UP odds
- Track engine performance across different match states and odds movements
- Identify any calculation issues before production implementation
- Provide clean, documented prototype for development team to replicate

## Constraints

- **Tech Stack**: Python 3.9+ with existing dependencies (playwright, httpx, numpy, pyyaml) - Must maintain compatibility
- **Database**: SQLite with existing schema - Can extend but not break existing tables
- **Execution Model**: Manual CLI execution - No server/daemon processes

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Use FTS_CALIBRATED_DP-PY engine without modification | Engine already produces accurate results, focus is validation not development | — Pending |
| Change-based scraping (check 1x2 diff before scraping) | Reduces unnecessary API calls, focuses data collection on actual odds movements | — Pending |
| Manual execution workflow | Trader controls when to collect data based on match timing and market activity | — Pending |
| Prototype as handoff to dev team | Trader owns validation, developers own production implementation | — Pending |

---
*Last updated: 2026-01-11 after initialization*
