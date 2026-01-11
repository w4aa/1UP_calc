# analyze_engines.py Fix Summary

## Problem

The original `analyze_engines.py` script treated 1UP as a complementary 2-way market (like Match Winner), which is **incorrect** because:

1. **Home 1UP and Away 1UP can both happen in the same match** - they are not mutually exclusive outcomes
2. The script used `devig_two_way()` to "de-vig" actual 1UP odds, which assumes `P(Home) + P(Away) = 1.0`
3. This caused incorrect "fair odds" calculations and misleading performance metrics

### Specific Issues Fixed

1. **`_actual_to_fair()` method** - Used 2-way devigging on 1UP odds (invalid)
2. **`_apply_margin_to_1up()` method** - Scaled probabilities using `total_fair` normalization (invalid for non-complementary market)
3. **Summary output** - Reported "Fair Odds Difference" based on incorrect 2-way fair conversion
4. **Misleading results** - Made FTS-Calibrated-DP look poor even when it was excellent

## Solution

### A) Removed 2-Way "Fairization"

**Before:**
```python
def _actual_to_fair(actual_home, actual_away):
    fair_prob_home = devig_two_way(actual_home, actual_away)  # WRONG!
    fair_prob_away = 1.0 - fair_prob_home  # Forces complementarity
    return 1/fair_prob_home, 1/fair_prob_away
```

**After:**
```python
# Removed _actual_to_fair() entirely
# Use raw implied probabilities instead:
sporty_imp_home = 1 / actual_sporty_home  # No normalization
sporty_imp_away = 1 / actual_sporty_away  # No normalization
```

### B) Compute Errors in Probability Space (Primary KPI)

**New Error Metrics:**
```python
# Probability errors (main metric)
err_prob_home_sporty = p_home_1up - sporty_imp_home
abs_err_prob_home_sporty = abs(err_prob_home_sporty)

# Log-odds errors (stable metric, less sensitive to longshots)
logodds_err_home_sporty = abs(log(fair_home) - log(actual_sporty_home))
```

**Why probability MAE is primary:**
- Odds MAE overweights longshots (error of 30 on 35.0→5.0 dominates error of 0.05 on 2.0→1.95)
- Probability MAE treats all outcomes fairly
- Log-odds MAE is stable but less intuitive

### C) Fixed Margin Application

**Before:**
```python
def _apply_margin_to_1up(p_home, p_away, margin):
    total_fair = p_home + p_away  # Assumes complementarity
    target_total = 1.0 + margin
    scale_factor = target_total / total_fair  # Normalizes to 1.0
    p_home_margin = p_home * scale_factor
    return 1/p_home_margin, ...
```

**After (per-selection margin):**
```python
def _apply_margin_to_1up(p_home, p_away, margin):
    # Odds-side margin: reduce fair odds by margin %
    fair_home_odds = 1.0 / p_home
    home_odds_with_margin = fair_home_odds * (1 - margin)
    return home_odds_with_margin, ...
```

### D) Updated Summary Output

**Before:**
```
Fair Odds Difference by Engine (fair - actual_fair):
  Engine                   Avg Home Diff    Avg Away Diff
  Poisson-Calibrated            0.2410          0.3640
  FTS-Calibrated-DP            -0.0282         -0.0350
```
(Misleading - based on incorrect 2-way devigging)

**After:**
```
[Probability MAE by Engine] (vs Sporty implied probs - same odds provider):
  Engine                        Home MAE     Away MAE    Records
  FTS-Calibrated-DP               0.0103       0.0086        248
  Poisson-Calibrated              0.0699       0.0634        248

[Log-Odds MAE by Engine] (vs Sporty):
  Engine                       Home Log-MAE    Away Log-MAE
  FTS-Calibrated-DP                  0.0166          0.0165
  Poisson-Calibrated                 0.1236          0.1431
```
(Correct - shows FTS engine is ~7x better for Pawa/Sporty)

## Results After Fix

### Betpawa (uses Sporty FTS)
- **FTS-Calibrated-DP: Home MAE 0.0103, Away MAE 0.0086** ✓ Excellent
- Poisson-Calibrated: Home MAE 0.0699, Away MAE 0.0634 ✗ Much worse
- **~7x improvement** with FTS engine

### Sportybet
- **FTS-Calibrated-DP: Home MAE 0.0108, Away MAE 0.0093** ✓ Excellent
- Poisson-Calibrated: Home MAE 0.0820, Away MAE 0.0765 ✗ Much worse
- **~8x improvement** with FTS engine

### Bet9ja
- FTS-Calibrated-DP: Home MAE 0.2620, Away MAE 0.3772 ✗ Poor
- **Poisson-Calibrated: Home MAE 0.0758, Away MAE 0.0665** ✓ Better
- Confirms our earlier finding that Bet9ja FTS structure is problematic

## CSV Output Changes

### New Columns Added
- `sporty_imp_home`, `sporty_imp_away` - Raw implied probabilities (no devigging)
- `err_prob_home_sporty`, `err_prob_away_sporty` - Signed probability errors
- `abs_err_prob_home_sporty`, `abs_err_prob_away_sporty` - Absolute probability errors (main KPI)
- `logodds_err_home_sporty`, `logodds_err_away_sporty` - Log-odds errors (stable metric)
- Similar columns for Bet9ja: `bet9ja_imp_home`, `abs_err_prob_home_bet9ja`, etc.

### Columns Removed
- `sporty_fair_h`, `sporty_fair_a` - Removed (were based on incorrect 2-way devigging)
- `home_fair_diff`, `away_fair_diff` - Removed (were based on incorrect fair odds)
- Similar for Bet9ja: `bet9ja_fair_h`, `bet9ja_fair_a`, etc.

## Testing

### Unit Tests (`test_analyze_engines.py`)
Created tests for:
- `odds_to_implied_prob()` conversion
- Edge cases (odds ≤ 1.0, None input)
- Division-by-zero safety

All tests pass:
```
============================================================
  ANALYZE_ENGINES.PY UNIT TESTS
============================================================
Testing odds_to_implied_prob()...
  [OK] odds=2.0 -> prob=0.5000
  [OK] odds=1.5 -> prob=0.6667
  [OK] odds=5.0 -> prob=0.2000
  [OK] Invalid odds return None
  [OK] None input returns None
  [OK] odds=1.01 -> prob=0.9901

Testing division-by-zero safety...
  [OK] Zero odds handled safely
  [OK] Very small odds handled safely

[PASS] All tests passed!
```

### Integration Testing
Verified with actual data:
```bash
python analyze_engines.py --bookmaker pawa --no-csv
python analyze_engines.py --bookmaker sporty --no-csv
python analyze_engines.py --bookmaker bet9ja --no-csv
```

All produce correct probability MAE metrics showing FTS engine excellence for Sporty/Pawa and Poisson superiority for Bet9ja.

## Key Takeaway

**1UP is NOT a complementary market.** Home 1UP @ 1.50 and Away 1UP @ 2.00 can both happen in the same match (e.g., Home leads 1-0, then Away equalizes 1-1 and goes ahead 2-1). Therefore:

- ✗ Don't use 2-way devigging
- ✗ Don't normalize probabilities to sum to 1.0
- ✓ Use raw implied probabilities: `p = 1 / odds`
- ✓ Compare in probability space with MAE as primary metric
- ✓ Use per-selection margin (no total_fair scaling)

This fix reveals the true performance: **FTS-Calibrated-DP is 7-8x better than Poisson-Calibrated for Sporty/Pawa 1UP pricing.**
