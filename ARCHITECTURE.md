# 1UP Calculator - Complete Architecture Guide

## Overview

The 1UP Calculator is a betting odds calculation system that:
1. **Scrapes** odds from 3 bookmakers (Sportybet, Betpawa, Bet9ja)
2. **Stores** them in a unified SQLite database
3. **Calculates** fair 1UP odds using Poisson-based Monte Carlo simulation
4. **Compares** calculated odds vs actual bookmaker odds to find value bets

---

## Complete Data Flow

### 1. SCRAPING PHASE (main.py → unified_scraper.py)

```
Tournament Config (config/tournaments.yaml)
    ↓
UnifiedScraper.run()
    ↓
Scrape 3 bookmakers in parallel:
    ├─ Sportybet (uses Playwright browser)
    ├─ Betpawa (uses HTTP/API)
    └─ Bet9ja (uses HTTP/API)
    ↓
Store in DB:
    - events table (one row per match)
    - markets table (one row per market per match)
```

**Key Files:**
- `src/unified_scraper.py` - Orchestrates all scraping
- `src/scraper/sporty/` - Sportybet scrapers
- `src/scraper/pawa/` - Betpawa scrapers
- `src/scraper/bet9ja/` - Bet9ja scrapers

---

### 2. DATABASE STRUCTURE (src/db/manager.py)

#### **markets table** - The Core Data Structure

This is THE MOST IMPORTANT table for engines. One row per market per match, with ALL bookmakers' odds in the same row:

```sql
CREATE TABLE markets (
    id INTEGER PRIMARY KEY,
    sportradar_id TEXT NOT NULL,        -- Unique match ID
    market_name TEXT NOT NULL,          -- "1X2", "Over/Under", "BTTS", etc.
    specifier TEXT DEFAULT '',          -- "2.5" for O/U 2.5, "" for 1X2

    -- SPORTYBET ODDS (3 outcomes max)
    sporty_market_id TEXT,
    sporty_outcome_1_name TEXT,         -- "Home", "Over", "Yes", etc.
    sporty_outcome_1_odds REAL,         -- 2.10
    sporty_outcome_2_name TEXT,         -- "Draw", "Under", "No", etc.
    sporty_outcome_2_odds REAL,         -- 3.40
    sporty_outcome_3_name TEXT,         -- "Away"
    sporty_outcome_3_odds REAL,         -- 3.20

    -- BETPAWA ODDS (3 outcomes max)
    pawa_market_id TEXT,
    pawa_outcome_1_name TEXT,
    pawa_outcome_1_odds REAL,
    pawa_outcome_2_name TEXT,
    pawa_outcome_2_odds REAL,
    pawa_outcome_3_name TEXT,
    pawa_outcome_3_odds REAL,

    -- BET9JA ODDS (3 outcomes max)
    bet9ja_market_id TEXT,
    bet9ja_outcome_1_name TEXT,
    bet9ja_outcome_1_odds REAL,
    bet9ja_outcome_2_name TEXT,
    bet9ja_outcome_2_odds REAL,
    bet9ja_outcome_3_name TEXT,
    bet9ja_outcome_3_odds REAL,

    scraped_at TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(sportradar_id, market_name, specifier)
)
```

**Example Row:**

```
sportradar_id: "sr:match:12345678"
market_name: "1X2"
specifier: ""
sporty_outcome_1_name: "Manchester United"
sporty_outcome_1_odds: 2.10
sporty_outcome_2_name: "Draw"
sporty_outcome_2_odds: 3.40
sporty_outcome_3_name: "Liverpool"
sporty_outcome_3_odds: 3.20
pawa_outcome_1_odds: 2.05
pawa_outcome_2_odds: 3.50
pawa_outcome_3_odds: 3.30
bet9ja_outcome_1_odds: 2.15
bet9ja_outcome_2_odds: 3.45
bet9ja_outcome_3_odds: 3.15
```

**Why this structure?**
- All bookmakers' odds for the same market are in ONE ROW
- Easy to compare odds across bookmakers
- Easy to query "give me all markets for this match"

---

### 3. ENGINE EXECUTION FLOW

#### **Step 1: Get All Markets for a Match**

```python
# In runner.py line 129
markets_raw = self.db.get_markets_for_event(sportradar_id)
```

This returns a list of dicts like:
```python
[
    {
        'sportradar_id': 'sr:match:12345',
        'market_name': '1X2',
        'specifier': '',
        'sporty_outcome_1_odds': 2.10,
        'sporty_outcome_2_odds': 3.40,
        'sporty_outcome_3_odds': 3.20,
        'pawa_outcome_1_odds': 2.05,
        'pawa_outcome_2_odds': 3.50,
        'pawa_outcome_3_odds': 3.30,
        'bet9ja_outcome_1_odds': 2.15,
        ...
    },
    {
        'market_name': 'Over/Under',
        'specifier': '2.5',
        'sporty_outcome_1_odds': 1.85,  # Over 2.5
        'sporty_outcome_2_odds': 2.05,  # Under 2.5
        ...
    },
    {
        'market_name': 'Home O/U',
        'specifier': '0.5',
        'sporty_outcome_1_odds': 1.40,  # Home Over 0.5
        'sporty_outcome_2_odds': 3.10,  # Home Under 0.5
        ...
    },
    ...
]
```

#### **Step 2: Run Engine for Each Bookmaker**

```python
# In runner.py lines 85-114
for engine in self.engines:
    for bookmaker in ['sporty', 'pawa', 'bet9ja']:
        # Prepare market data for this bookmaker
        data = self._prepare_market_data(markets_raw, bookmaker)

        # Run engine calculation
        result = engine.calculate(data, bookmaker)
```

#### **Step 3: Prepare Market Data (_prepare_market_data)**

This is where the magic happens! The runner extracts specific markets from the raw data:

```python
# runner.py lines 469-491
def _prepare_market_data(self, markets: list[dict], bookmaker: str) -> dict:
    """
    Takes all markets for a match and bookmaker,
    returns structured dict with only the odds needed by engines.
    """

    # Extract 1X2 odds
    home_1x2, draw_1x2, away_1x2 = self._get_1x2_odds(markets, bookmaker)

    # Extract Over/Under 2.5 odds
    total_line, total_over, total_under = self._find_ou_market(
        markets, "Over/Under", bookmaker, 2.5
    )

    # Extract Home O/U 0.5 odds
    home_line, home_over, home_under = self._find_ou_market(
        markets, "Home O/U", bookmaker, 0.5
    )

    # Extract Away O/U 0.5 odds
    away_line, away_over, away_under = self._find_ou_market(
        markets, "Away O/U", bookmaker, 0.5
    )

    # Other markets...
    btts_yes, btts_no = self._get_btts_odds(markets, bookmaker)
    asian_handicap = self._get_asian_handicap_odds(markets, bookmaker)

    return {
        '1x2': (home_1x2, draw_1x2, away_1x2),
        'total_ou': (total_line, total_over, total_under),
        'home_ou': (home_line, home_over, home_under),
        'away_ou': (away_line, away_over, away_under),
        'btts': (btts_yes, btts_no),
        'asian_handicap': asian_handicap,
    }
```

**Example result for Sportybet:**
```python
{
    '1x2': (2.10, 3.40, 3.20),  # Home, Draw, Away
    'total_ou': (2.5, 1.85, 2.05),  # Line, Over, Under
    'home_ou': (0.5, 1.40, 3.10),
    'away_ou': (0.5, 1.55, 2.50),
    'btts': (1.75, 2.10),  # Yes, No
    'asian_handicap': {
        -1.0: (1.95, 1.95),  # Home -1, Away +1
        0.0: (2.50, 1.65),   # Home 0, Away 0
    }
}
```

#### **Step 4: Helper Functions for Extracting Markets**

**_get_market_odds** - The universal market finder:
```python
# runner.py lines 493-514
def _get_market_odds(self, markets: list[dict], market_name: str, specifier: str = ""):
    """
    Find a specific market in the list and return odds for ALL bookmakers.
    """
    for m in markets:
        if m['market_name'] == market_name and m['specifier'] == specifier:
            return {
                'sporty': {
                    'outcome_1': m['sporty_outcome_1_odds'],
                    'outcome_2': m['sporty_outcome_2_odds'],
                    'outcome_3': m['sporty_outcome_3_odds'],
                },
                'pawa': {
                    'outcome_1': m['pawa_outcome_1_odds'],
                    'outcome_2': m['pawa_outcome_2_odds'],
                    'outcome_3': m['pawa_outcome_3_odds'],
                },
                'bet9ja': {
                    'outcome_1': m.get('bet9ja_outcome_1_odds'),
                    'outcome_2': m.get('bet9ja_outcome_2_odds'),
                    'outcome_3': m.get('bet9ja_outcome_3_odds'),
                }
            }
    return None
```

**_get_1x2_odds** - Extract 1X2 for a specific bookmaker:
```python
# runner.py lines 516-521
def _get_1x2_odds(self, markets: list[dict], bookmaker: str) -> tuple:
    m = self._get_market_odds(markets, "1X2", "")
    if not m:
        return None, None, None
    odds = m[bookmaker]  # Get just the bookmaker we want
    return odds['outcome_1'], odds['outcome_2'], odds['outcome_3']
```

**_find_ou_market** - Find Over/Under market (handles multiple lines):
```python
# runner.py lines 542-601
def _find_ou_market(self, markets, market_name, bookmaker, preferred_line):
    """
    Find Over/Under market, prefer half-lines (.5) and preferred_line.
    Example: For "Over/Under", prefers 2.5 over 2.0 or 3.0
    """
    candidates = []
    for m in markets:
        if m['market_name'] != market_name:
            continue

        line = float(m['specifier'])  # "2.5" -> 2.5

        if bookmaker == 'sporty':
            over_odds = m['sporty_outcome_1_odds']
            under_odds = m['sporty_outcome_2_odds']
        elif bookmaker == 'pawa':
            over_odds = m['pawa_outcome_1_odds']
            under_odds = m['pawa_outcome_2_odds']
        # ... bet9ja similar

        if over_odds and under_odds:
            candidates.append((line, over_odds, under_odds))

    if not candidates:
        return None, None, None

    # Prefer half-lines (.5)
    half_lines = [x for x in candidates if x[0] % 1 == 0.5]
    if half_lines:
        # Find exact match to preferred_line
        exact = [x for x in half_lines if abs(x[0] - preferred_line) < 0.01]
        if exact:
            return exact[0]  # Perfect match!
        return half_lines[0]  # Any half-line

    return candidates[0]  # Fallback to first available
```

---

### 4. ENGINE CALCULATION (CalibratedPoissonEngine)

Now the engine receives the prepared data dict:

```python
# poisson_calibrated.py lines 173-303
def calculate(self, markets: dict, bookmaker: str) -> dict:
    """
    Input: markets dict from _prepare_market_data
    Output: dict with calculated 1UP odds
    """

    # 1. Extract required markets
    x1x2 = markets.get('1x2')  # (2.10, 3.40, 3.20)
    total_ou = markets.get('total_ou')  # (2.5, 1.85, 2.05)
    home_ou = markets.get('home_ou')  # (0.5, 1.40, 3.10)
    away_ou = markets.get('away_ou')  # (0.5, 1.55, 2.50)

    if not all([x1x2, total_ou, home_ou, away_ou]):
        return None  # Can't calculate without these markets

    # 2. De-vig 1X2 to get fair probabilities
    p_home_win, p_draw, p_away_win = devig_three_way(*x1x2)

    # 3. Infer Poisson lambdas from team totals
    lambda_home = fit_lambda_from_ou_lines(home_ou)  # Expected goals home
    lambda_away = fit_lambda_from_ou_lines(away_ou)  # Expected goals away

    # 4. Infer total expected goals from total O/U
    lambda_total = fit_lambda_from_ou_lines(total_ou)

    # 5. Rescale to match total
    factor = lambda_total / (lambda_home + lambda_away)
    lambda_home *= factor
    lambda_away *= factor

    # 6. Optimize supremacy to match 1X2 probabilities
    # ... (complex optimization, see code)

    # 7. Run Monte Carlo simulation
    p_home_1up_raw, p_away_1up_raw = simulate_1up_probabilities(
        lambda_home, lambda_away,
        n_sims=30000,
        match_minutes=95
    )

    # 8. Apply empirical corrections for underdog bias
    p_home_1up, p_away_1up = correct_1up_probabilities(
        p_home_1up_raw, p_away_1up_raw,
        lambda_home, lambda_away
    )

    # 9. Convert probabilities to fair odds
    fair_home = 1.0 / p_home_1up
    fair_away = 1.0 / p_away_1up
    fair_draw = draw_1x2  # Use bookmaker's draw odds as-is

    return {
        'engine': 'Poisson-Calibrated',
        'lambda_home': lambda_home,
        'lambda_away': lambda_away,
        'lambda_total': lambda_total,
        'p_home_1up': p_home_1up,
        'p_away_1up': p_away_1up,
        '1up_home_fair': fair_home,
        '1up_away_fair': fair_away,
        '1up_draw': fair_draw,
    }
```

---

### 5. STORING RESULTS

```python
# runner.py lines 95-113
results.append({
    'sportradar_id': sportradar_id,
    'engine_name': 'Poisson-Calibrated',
    'bookmaker': bookmaker,  # 'sporty', 'pawa', or 'bet9ja'
    'lambda_home': 1.45,
    'lambda_away': 1.23,
    'lambda_total': 2.68,
    'p_home_1up': 0.65,
    'p_away_1up': 0.55,
    'fair_home': 1.54,  # Our calculated fair odd
    'fair_away': 1.82,  # Our calculated fair odd
    'fair_draw': 3.40,  # Bookmaker's draw odd
    'actual_sporty_home': 2.10,  # Actual 1UP odd from Sportybet
    'actual_sporty_away': 3.20,  # (if available)
    'actual_bet9ja_home': 2.15,  # Actual 1UP odd from Bet9ja
    'actual_bet9ja_away': 3.15,  # (if available)
})
```

These are stored in the `engine_calculations` table.

---

## Key Concepts for New Engine Development

### 1. **Market Data Input**

Your engine receives a dict with this structure:
```python
{
    '1x2': (home_odds, draw_odds, away_odds),
    'total_ou': (line, over_odds, under_odds),
    'home_ou': (line, over_odds, under_odds),
    'away_ou': (line, over_odds, under_odds),
    'btts': (yes_odds, no_odds),
    'asian_handicap': {
        -1.0: (home_odds, away_odds),
        0.0: (home_odds, away_odds),
        +1.0: (home_odds, away_odds),
    },
    # Add more markets as needed...
}
```

### 2. **What You Must Return**

Your engine must return a dict with these keys:
```python
{
    'engine': 'YourEngineName',
    'lambda_home': float,       # Expected goals home
    'lambda_away': float,       # Expected goals away
    'lambda_total': float,      # Total expected goals
    'p_home_1up': float,        # Probability Home leads by 1+ at any point
    'p_away_1up': float,        # Probability Away leads by 1+ at any point
    '1up_home_fair': float,     # Your fair odd for Home 1UP
    '1up_away_fair': float,     # Your fair odd for Away 1UP
    '1up_draw': float,          # Draw odd (usually copied from bookmaker)
}
```

### 3. **Adding New Markets to Input**

If you need a new market (e.g., "Corners", "Cards"):

**Step 1:** Add to `_prepare_market_data` in runner.py:
```python
def _prepare_market_data(self, markets: list[dict], bookmaker: str) -> dict:
    # ... existing code ...

    # Add new market
    corners_over, corners_under = self._get_corners_odds(markets, bookmaker)

    return {
        # ... existing markets ...
        'corners': (corners_over, corners_under),
    }
```

**Step 2:** Add helper function:
```python
def _get_corners_odds(self, markets: list[dict], bookmaker: str) -> tuple:
    m = self._get_market_odds(markets, "Total Corners", "10.5")
    if not m:
        return None, None
    odds = m[bookmaker]
    return odds['outcome_1'], odds['outcome_2']
```

**Step 3:** Use in your engine:
```python
def calculate(self, markets: dict, bookmaker: str):
    corners = markets.get('corners')
    if corners:
        corners_over, corners_under = corners
        # Use this data in your calculations...
```

### 4. **Running Multiple Calculations per Match**

The current system runs 3 calculations per match (one per bookmaker):
- Calculation 1: Using Sportybet odds as input
- Calculation 2: Using Betpawa odds as input
- Calculation 3: Using Bet9ja odds as input

This allows comparing:
- Does Sportybet's odds suggest Home 1UP is 1.54 fair?
- Does Betpawa's odds suggest Home 1UP is 1.52 fair?
- Does Bet9ja's odds suggest Home 1UP is 1.56 fair?

Then compare each to actual 1UP odds from Sportybet and Bet9ja.

---

## Execution Modes

### Mode 1: Scrape Only
```bash
python main.py --scrape
```
- Scrapes odds from all bookmakers
- Updates `events` and `markets` tables
- Does NOT run engines

### Mode 2: Engines Only
```bash
python main.py --engines
```
- Reads existing odds from database
- Runs engines on all matched events
- Stores calculations in `engine_calculations` table

### Mode 3: Full Pipeline
```bash
python main.py
```
- Scrapes odds
- Runs engines
- Complete end-to-end

---

## Database Schema Summary

```
tournaments          → Tournament configurations
    ↓
events              → Match records (one per match)
    ↓
markets             → Market odds (multiple per match, all bookmakers in one row)
    ↓
scraping_history    → Scraping sessions (timestamps)
    ↓
market_snapshots    → Historical snapshots of odds
    ↓
engine_calculations → Engine results (multiple per match)
```

---

## Questions for Your New Engine?

1. **What markets do you need as input?** (We can add them easily)
2. **What's your calculation methodology?** (Poisson? Machine learning? Different simulation?)
3. **Do you need historical data?** (We have snapshots over time)
4. **Do you want to use multiple bookmakers' odds?** (Currently we run once per bookmaker)
5. **What should we store as output?** (We can add columns to engine_calculations)

Let me know and I'll help you design the integration!
