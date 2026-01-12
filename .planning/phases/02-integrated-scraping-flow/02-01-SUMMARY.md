---
phase: 02-integrated-scraping-flow
plan: 01
subsystem: scraping
tags: [betpawa, change-detection, sequential-flow, multi-bookmaker]

# Dependency graph
requires:
  - phase: 01-change-detection
    provides: snapshot-based 1x2 odds comparison via market_snapshots table
provides:
  - BetPawa-first change detection phase for tournament processing
  - Sequential scraping flow triggered by BetPawa 1x2 changes
  - Event filtering for conditional multi-bookmaker scraping
affects: [03-engine-configuration]

# Tech tracking
tech-stack:
  added: []
  patterns: [sequential-scraping, change-based-triggering, event-filtering]

key-files:
  created: []
  modified: [src/unified_scraper.py]

key-decisions:
  - "BetPawa acts as change detector, triggering all bookmaker scraping"
  - "Sequential flow: BetPawa check → conditional scraping → snapshots"
  - "Event filtering applied after fetching to preserve event storage"
  - "Change detection removed from Sporty/Pawa scrapers (BetPawa handles it)"

patterns-established:
  - "BetPawa-first sequential flow with early return optimization"
  - "Filter-based event scraping for efficient data collection"

issues-created: []

# Metrics
duration: 35min
completed: 2026-01-12
---

# Phase 2 Plan 1: Integrated Scraping Flow Summary

**Refactored scraping orchestration to BetPawa-triggered sequential flow where 1x2 odds changes drive all bookmaker data collection**

## Performance

- **Duration:** 35 min
- **Started:** 2026-01-12T08:14:27Z
- **Completed:** 2026-01-12T08:49:27Z
- **Tasks:** 3
- **Files modified:** 1

## Accomplishments

- Created `_check_betpawa_changes_for_tournament` method that fetches BetPawa events and 1x2 odds, checks for changes against last snapshot, and returns dict of changed events
- Refactored `_process_tournament` to implement BetPawa-first sequential flow with three phases: (1) BetPawa change detection, (2) conditional multi-bookmaker scraping, (3) snapshot creation
- Updated all three scraper methods (`_scrape_sportybet`, `_scrape_betpawa`, `_scrape_bet9ja`) to accept `filter_sportradar_ids` parameter and filter events after fetching
- Removed per-bookmaker change detection from Sporty and Pawa scrapers (BetPawa now handles all change detection)
- Added early return optimization: skip tournament entirely if no BetPawa 1x2 changes detected

## Task Commits

Each task was committed atomically:

1. **Task 1: Create BetPawa change detection phase** - `8458ce4` (feat)
2. **Task 2: Refactor tournament orchestration to sequential BetPawa-triggered flow** - `4571004` (feat)
3. **Task 3: Update scraper methods to accept and honor event filter** - `82442a1` (feat)

## Files Created/Modified

- `src/unified_scraper.py` - Implemented BetPawa-first sequential scraping flow with change detection phase, conditional multi-bookmaker scraping triggered by BetPawa 1x2 changes, and event filtering for all scrapers

## Decisions Made

1. **BetPawa as change detector**: BetPawa 1x2 odds check runs first for all tournaments, acting as gatekeeper for all scraping decisions
2. **Sequential flow with early return**: If BetPawa detects no 1x2 changes (and not force mode), skip tournament entirely to avoid unnecessary scraping
3. **Event filtering after fetch**: Filter is applied after fetching events to preserve event storage in database, but before market scraping
4. **Removed internal change detection**: Sporty and Pawa scrapers no longer check their own 1x2 odds - BetPawa's detection drives all decisions

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None

## Next Phase Readiness

Phase 2 Plan 1 complete. Ready for Phase 3: Engine Configuration & Validation.

All verification checks passed:
- ✓ `_check_betpawa_changes_for_tournament` method exists and returns changed events dict
- ✓ `_process_tournament` calls BetPawa change detection first, returns early if no changes
- ✓ `_process_tournament` passes filter_sportradar_ids to all scraper methods
- ✓ All scraper methods accept and honor filter parameter
- ✓ No per-bookmaker change detection remains in Sporty/Pawa scraper methods
- ✓ Python syntax check passes
- ✓ Logs clearly show BetPawa-first flow with filtering messages

---
*Phase: 02-integrated-scraping-flow*
*Completed: 2026-01-12*
