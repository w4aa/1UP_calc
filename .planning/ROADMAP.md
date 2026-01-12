# Roadmap: 1UP Calculation Prototype

## Overview

This roadmap transforms the existing 1UP calculation system from manual execution to an intelligent change-based workflow. Starting with change detection to identify when BetPawa 1x2 odds shift, we integrate the scraping pipeline to collect competitor data only when needed. We then add engine calibration controls and verify automatic calculation execution, complete the end-to-end data flow, validate data quality across all scrapers, and finally prepare the codebase for stakeholder review and developer handoff.

## Domain Expertise

None

## Phases

- [x] **Phase 1: Change Detection Foundation** - Implement 1x2 odds comparison logic
- [x] **Phase 2: Integrated Scraping Flow** - Connect change detection to scraping pipeline
- [x] **Phase 3: Engine Configuration & Validation** - Add calibration config and verify execution
- [ ] **Phase 4: End-to-End Data Flow** - Complete tournament to storage pipeline
- [ ] **Phase 5: Data Quality Validation** - Ensure scrapers run smoothly
- [ ] **Phase 6: Code Documentation & Cleanup** - Prepare for handoff

## Phase Details

### Phase 1: Change Detection Foundation
**Goal**: Implement logic to compare new BetPawa 1x2 odds against last market_snapshot and determine if scraping is needed
**Depends on**: Nothing (first phase)
**Research**: Unlikely (internal database queries and comparison logic)
**Plans**: 1/1 complete
**Status**: Complete (2026-01-11)

### Phase 2: Integrated Scraping Flow
**Goal**: Connect change detection to multi-bookmaker scraping pipeline so scraping only happens when 1x2 odds change
**Depends on**: Phase 1
**Research**: Unlikely (existing scrapers, just connecting the flow)
**Plans**: 1/1 complete
**Status**: Complete (2026-01-12)

### Phase 3: Engine Configuration & Validation
**Goal**: Add config system for engine probability skew (home/away adjustments with ±#.###0 precision), verify automatic execution works correctly, and ensure engines only calculate new snapshots (skip if sportradar_id + history_id already exists in engine_calculations)
**Depends on**: Phase 2
**Research**: Unlikely (internal engine code review and config addition)
**Plans**: 1/1 complete
**Status**: Complete (2026-01-12)

### Phase 4: End-to-End Data Flow
**Goal**: Complete tournament → events → check → scrape → calculate → store pipeline with all components working together
**Depends on**: Phase 3
**Research**: Unlikely (integrating existing components)
**Plans**: TBD

### Phase 5: Data Quality Validation
**Goal**: Ensure scrapers run smoothly, handle edge cases, verify data integrity across all bookmakers
**Depends on**: Phase 4
**Research**: Unlikely (testing and validation of existing scrapers)
**Plans**: TBD

### Phase 6: Code Documentation & Cleanup
**Goal**: Prepare codebase for stakeholder review and developer handoff with clear documentation and clean structure
**Depends on**: Phase 5
**Research**: Unlikely (documentation and refactoring)
**Plans**: TBD

## Progress

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Change Detection Foundation | 1/1 | Complete | 2026-01-11 |
| 2. Integrated Scraping Flow | 1/1 | Complete | 2026-01-12 |
| 3. Engine Configuration & Validation | 1/1 | Complete | 2026-01-12 |
| 4. End-to-End Data Flow | 0/TBD | Not started | - |
| 5. Data Quality Validation | 0/TBD | Not started | - |
| 6. Code Documentation & Cleanup | 0/TBD | Not started | - |
