# 1UP Calculator - Data Flow Diagram

## Complete Flow: From Scraping to Engine Results

```
┌─────────────────────────────────────────────────────────────────┐
│                    SCRAPING PHASE (main.py)                      │
└─────────────────────────────────────────────────────────────────┘
                              ↓
        ┌─────────────────────────────────────────────┐
        │      UnifiedScraper (unified_scraper.py)    │
        └─────────────────────────────────────────────┘
                              ↓
    ┌──────────────────┬────────────┬──────────────────┐
    ↓                  ↓            ↓                  ↓
┌─────────┐      ┌─────────┐   ┌─────────┐      ┌─────────┐
│Sportybet│      │ Betpawa │   │ Bet9ja  │      │Tournaments│
│ Scraper │      │ Scraper │   │ Scraper │      │  Config  │
└─────────┘      └─────────┘   └─────────┘      └─────────┘
    │                  │            │                  │
    └──────────────────┴────────────┴──────────────────┘
                              ↓
        ┌─────────────────────────────────────────────┐
        │         SQLite Database (datas.db)          │
        ├─────────────────────────────────────────────┤
        │  ┌─────────────────────────────────────┐   │
        │  │  events table                       │   │
        │  │  - One row per match                │   │
        │  │  - sportradar_id (unique)           │   │
        │  │  - home_team, away_team             │   │
        │  └─────────────────────────────────────┘   │
        │                   ↓                         │
        │  ┌─────────────────────────────────────┐   │
        │  │  markets table (THE MAIN DATA!)     │   │
        │  │  - One row per market per match     │   │
        │  │  - All 3 bookmakers in same row:    │   │
        │  │    * sporty_outcome_1_odds          │   │
        │  │    * pawa_outcome_1_odds            │   │
        │  │    * bet9ja_outcome_1_odds          │   │
        │  │  - market_name: "1X2", "Over/Under"│   │
        │  │  - specifier: "2.5" for O/U 2.5     │   │
        │  └─────────────────────────────────────┘   │
        └─────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│                    ENGINE PHASE (main.py)                        │
└─────────────────────────────────────────────────────────────────┘
                              ↓
        ┌─────────────────────────────────────────────┐
        │       EngineRunner (engine/runner.py)       │
        └─────────────────────────────────────────────┘
                              ↓
        ┌─────────────────────────────────────────────┐
        │  For each match with matched = 1:           │
        │    1. Get all markets (SQL query)           │
        │    2. For each bookmaker (sporty/pawa/9ja): │
        │       - Extract needed odds                 │
        │       - Run engine calculation              │
        │       - Store result                        │
        └─────────────────────────────────────────────┘
                              ↓
                       ┌────────────┐
                       │   STEP 1   │
                       └────────────┘
        ┌─────────────────────────────────────────────┐
        │  db.get_markets_for_event(sportradar_id)   │
        │  Returns: list of market dicts              │
        └─────────────────────────────────────────────┘
                              ↓
                   [Example for match 12345]
        ┌─────────────────────────────────────────────┐
        │ [                                           │
        │   {                                         │
        │     'market_name': '1X2',                   │
        │     'specifier': '',                        │
        │     'sporty_outcome_1_odds': 2.10,  # Home │
        │     'sporty_outcome_2_odds': 3.40,  # Draw │
        │     'sporty_outcome_3_odds': 3.20,  # Away │
        │     'pawa_outcome_1_odds': 2.05,            │
        │     'pawa_outcome_2_odds': 3.50,            │
        │     'pawa_outcome_3_odds': 3.30,            │
        │     'bet9ja_outcome_1_odds': 2.15,          │
        │     'bet9ja_outcome_2_odds': 3.45,          │
        │     'bet9ja_outcome_3_odds': 3.15,          │
        │   },                                        │
        │   {                                         │
        │     'market_name': 'Over/Under',            │
        │     'specifier': '2.5',                     │
        │     'sporty_outcome_1_odds': 1.85,  # Over │
        │     'sporty_outcome_2_odds': 2.05,  # Under│
        │     'pawa_outcome_1_odds': 1.90,            │
        │     'pawa_outcome_2_odds': 2.00,            │
        │     ...                                     │
        │   },                                        │
        │   {                                         │
        │     'market_name': 'Home O/U',              │
        │     'specifier': '0.5',                     │
        │     'sporty_outcome_1_odds': 1.40,          │
        │     'sporty_outcome_2_odds': 3.10,          │
        │     ...                                     │
        │   },                                        │
        │   ... (more markets)                        │
        │ ]                                           │
        └─────────────────────────────────────────────┘
                              ↓
                       ┌────────────┐
                       │   STEP 2   │
                       └────────────┘
        ┌─────────────────────────────────────────────┐
        │  _prepare_market_data(markets, 'sporty')   │
        │  Extract needed odds from raw market list   │
        └─────────────────────────────────────────────┘
                              ↓
          [Uses helper functions to find markets]
        ┌─────────────────────────────────────────────┐
        │ _get_market_odds('1X2', '') → finds row     │
        │   returns: {                                │
        │     'sporty': {outcome_1: 2.10, ...},      │
        │     'pawa': {outcome_1: 2.05, ...},        │
        │     'bet9ja': {outcome_1: 2.15, ...}       │
        │   }                                         │
        │                                             │
        │ _get_1x2_odds(markets, 'sporty')           │
        │   returns: (2.10, 3.40, 3.20)              │
        │                                             │
        │ _find_ou_market(markets, 'Over/Under',     │
        │                 'sporty', 2.5)              │
        │   returns: (2.5, 1.85, 2.05)               │
        │            (line, over, under)              │
        └─────────────────────────────────────────────┘
                              ↓
          [Returns structured dict for engine]
        ┌─────────────────────────────────────────────┐
        │ {                                           │
        │   '1x2': (2.10, 3.40, 3.20),               │
        │   'total_ou': (2.5, 1.85, 2.05),           │
        │   'home_ou': (0.5, 1.40, 3.10),            │
        │   'away_ou': (0.5, 1.55, 2.50),            │
        │   'btts': (1.75, 2.10),                    │
        │   'asian_handicap': {                       │
        │     -1.0: (1.95, 1.95),                    │
        │     0.0: (2.50, 1.65),                     │
        │   }                                         │
        │ }                                           │
        └─────────────────────────────────────────────┘
                              ↓
                       ┌────────────┐
                       │   STEP 3   │
                       └────────────┘
        ┌─────────────────────────────────────────────┐
        │   engine.calculate(prepared_data, 'sporty') │
        │                                             │
        │   CalibratedPoissonEngine does:             │
        │   1. Extract markets from dict              │
        │   2. De-vig 1X2 odds                        │
        │   3. Infer lambda from O/U markets          │
        │   4. Run Monte Carlo simulation             │
        │   5. Apply corrections                      │
        │   6. Return result dict                     │
        └─────────────────────────────────────────────┘
                              ↓
                     [Engine returns]
        ┌─────────────────────────────────────────────┐
        │ {                                           │
        │   'engine': 'Poisson-Calibrated',           │
        │   'lambda_home': 1.45,                      │
        │   'lambda_away': 1.23,                      │
        │   'lambda_total': 2.68,                     │
        │   'p_home_1up': 0.65,  # 65% chance        │
        │   'p_away_1up': 0.55,  # 55% chance        │
        │   '1up_home_fair': 1.54,  # 1/0.65 = 1.54  │
        │   '1up_away_fair': 1.82,  # 1/0.55 = 1.82  │
        │   '1up_draw': 3.40,                         │
        │ }                                           │
        └─────────────────────────────────────────────┘
                              ↓
                       ┌────────────┐
                       │   STEP 4   │
                       └────────────┘
        ┌─────────────────────────────────────────────┐
        │  Store to engine_calculations table:        │
        │                                             │
        │  - sportradar_id: 'sr:match:12345'         │
        │  - engine_name: 'Poisson-Calibrated'       │
        │  - bookmaker: 'sporty'                      │
        │  - lambda_home: 1.45                        │
        │  - lambda_away: 1.23                        │
        │  - fair_home: 1.54  (calculated)           │
        │  - fair_away: 1.82  (calculated)           │
        │  - actual_sporty_home: 2.10 (from market)  │
        │  - actual_sporty_away: 3.20 (from market)  │
        │  - actual_bet9ja_home: 2.15 (from market)  │
        │  - actual_bet9ja_away: 3.15 (from market)  │
        └─────────────────────────────────────────────┘
                              ↓
                    [Repeat for pawa]
                    [Repeat for bet9ja]
                              ↓
        ┌─────────────────────────────────────────────┐
        │  Result: 3 calculations per match           │
        │  (one using sporty odds, pawa odds, 9ja)    │
        └─────────────────────────────────────────────┘

═══════════════════════════════════════════════════════════════════

## KEY INSIGHT: The Markets Table Structure

The genius of this design is that ONE ROW contains ALL bookmakers:

```
Row 1: 1X2 market for match 12345
├─ sporty_outcome_1_odds: 2.10
├─ pawa_outcome_1_odds: 2.05
└─ bet9ja_outcome_1_odds: 2.15
```

This means:
✓ Easy to compare odds across bookmakers
✓ Easy to get all data for one match
✓ No complex joins needed
✓ Fast queries

═══════════════════════════════════════════════════════════════════

## Your New Engine Integration Points

### Where to Hook In:

1. **Input Preparation** (runner.py:_prepare_market_data)
   - Add new markets you need
   - Extract odds from database format

2. **Engine Calculation** (your_engine.py:calculate)
   - Receive prepared dict
   - Do your magic
   - Return standard format dict

3. **Output Storage** (runner.py:_compute_event)
   - Results automatically stored
   - Can add new columns to engine_calculations table

### What You Get For Free:

✓ Parallel scraping from 3 bookmakers
✓ Automatic market normalization
✓ Historical snapshots
✓ 1X2 change detection
✓ Multi-threaded engine execution
✓ Automatic result storage

### What You Need to Provide:

□ calculate(markets: dict, bookmaker: str) → dict
  - Input: prepared market data
  - Output: your calculated odds + metadata

That's it! The framework handles everything else.
