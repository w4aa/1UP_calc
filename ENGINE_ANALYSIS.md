# Poisson Calibrated Engine - Performance Analysis

**Date:** 2026-01-08
**Dataset:** 117 matches (pawa bookmaker calculations)
**Target:** Improve fair odds accuracy for 1UP markets

---

## 1. OVERALL ERROR METRICS

| Metric | Value | Status |
|--------|-------|--------|
| **Home MAE** | 0.1023 | Acceptable |
| **Away MAE** | 0.1918 | ⚠️ High |
| **Home Bias** | -0.0034 | Near-perfect |
| **Away Bias** | +0.0443 | ⚠️ Overpricing |

**Key Finding:** Away side has 2x higher error than home side, with systematic overpricing bias.

---

## 2. UNDERDOG vs FAVORITE BIAS ⚠️ CRITICAL ISSUE

| Metric | Value | Interpretation |
|--------|-------|----------------|
| **Underdog Bias** | **+0.0883** | ⚠️ Significant Overpricing |
| **Favorite Bias** | **-0.0474** | Underpricing |
| **Underdog MAE** | 0.2175 | Very High |
| **Favorite MAE** | 0.0767 | Acceptable |

### Analysis
- **Engine systematically OVERPRICES underdogs** by ~8.8% on average
- **Engine UNDERPRICES favorites** by ~4.7%
- Current correction factors (0.90-0.97) are **INSUFFICIENT**
- Error is **2.8x higher for underdogs** than favorites

---

## 3. ERROR BY LAMBDA RATIO (Team Imbalance)

### Balanced Matches (Ratio 1.0-1.2) - 27 matches
- **Underdog Error:** -0.058 (underpricing)
- **Favorite Error:** -0.058 (underpricing)
- **Problem:** Engine underprices BOTH sides in balanced matches
- **Recommendation:** **Remove or reduce correction** for ratio < 1.2

### Slight Imbalance (Ratio 1.2-1.5) - 23 matches
- **Underdog Error:** -0.031 (slight underpricing)
- **Favorite Error:** -0.031 (slight underpricing)
- **Status:** Near-optimal performance
- **Recommendation:** Keep current correction (~0.97)

### Moderate Imbalance (Ratio 1.5-2.0) - 35 matches
- **Underdog Error:** +0.057 (overpricing)
- **Favorite Error:** -0.021 (slight underpricing)
- **Problem:** Underdog overpriced, favorite underpriced
- **Recommendation:** Increase underdog correction to ~0.92

### High Imbalance (Ratio 2.0-3.0) - 24 matches
- **Underdog Error:** +0.076 ⚠️
- **Favorite Error:** +0.092 ⚠️
- **Problem:** BOTH sides overpriced (market is tighter than model)
- **Recommendation:** Apply **symmetric correction** - reduce both by 8-10%

### Extreme Imbalance (Ratio > 3.0) - 8 matches ⚠️ WORST
- **Underdog Error:** **+0.447** 🔴 CRITICAL
- **Favorite Error:** +0.064
- **Underdog MAE:** **0.613** (3x higher than overall)
- **Problem:** Massive overpricing of extreme underdogs
- **Recommendation:** **Aggressive correction** - reduce underdog to 0.75-0.80

---

## 4. WORST PREDICTIONS (Top Issues)

### Extreme Mismatch Examples:

**Atletico Madrid vs Deportivo Alaves** (Ratio 3.69)
- Lambda: Home=1.815, Away=0.491
- Away (underdog): Fair=5.341, Actual=4.149, **Error=+1.192** 🔴
- **Issue:** Underdog overpriced by 28%

**Bayern Munich vs Union Saint-Gilloise** (Ratio 2.61)
- Lambda: Home=2.592, Away=0.992
- Away (underdog): Fair=3.520, Actual=4.613, **Error=-1.093** 🔴
- **Issue:** Underdog UNDERpriced (favorite overpriced instead)

**Mali vs Senegal** (Ratio 2.47)
- Lambda: Home=0.585, Away=1.444
- Home (underdog): Fair=4.102, Actual=3.261, **Error=+0.841**
- **Issue:** Consistent underdog overpricing

---

## 5. ROOT CAUSES

### Issue 1: Empirical Correction Function is Too Conservative
```python
# Current (poisson_calibrated.py lines 66-98)
def get_underdog_correction(ratio: float) -> float:
    if ratio <= 1.2:
        return 1.0 - 0.03 * (ratio - 1.0) / 0.2      # 0.97-1.00
    elif ratio <= 1.8:
        return 0.97 - 0.04 * (ratio - 1.2) / 0.6     # 0.93-0.97
    elif ratio <= 2.5:
        return 0.93 - 0.03 * (ratio - 1.8) / 0.7     # 0.90-0.93
    else:
        return 0.90 + 0.02 * min((ratio - 2.5) / 1.5, 1.0)  # 0.90-0.92
```

**Problems:**
- Ratio > 3.0 only gets 0.90-0.92 correction (should be 0.75-0.80)
- Ratio < 1.2 gets unnecessary correction (causes underpricing)
- Favorite correction is flat 0.97 (should vary by ratio)

### Issue 2: Supremacy Optimization Uses Corrected Lambdas
Line 224: `l_home_corr, l_away_corr = empirical_underdog_correction(l_home, l_away)`
- This applies lambda-level correction BEFORE calculating supremacy
- Then probability correction is applied AGAIN (double correction)
- **Fix:** Remove lambda correction from supremacy calculation

### Issue 3: Favorite Correction is Insufficient
```python
# Current (line 101-115)
def get_favorite_correction(ratio: float) -> float:
    return 0.97  # Flat 3% reduction
```
- For high ratios (>2.0), favorites need MORE correction (~0.92-0.93)
- Current flat 0.97 is too conservative

---

## 6. RECOMMENDED FIXES

### Fix 1: Revised Underdog Correction Function

```python
def get_underdog_correction(ratio: float) -> float:
    """
    Revised correction based on 117-match analysis.
    More aggressive for extreme mismatches.
    """
    if ratio <= 1.15:
        # Balanced: NO correction needed
        return 1.0
    elif ratio <= 1.5:
        # Slight: minimal correction (0.97-1.00)
        return 1.0 - 0.03 * (ratio - 1.15) / 0.35
    elif ratio <= 2.0:
        # Moderate: standard correction (0.92-0.97)
        return 0.97 - 0.05 * (ratio - 1.5) / 0.5
    elif ratio <= 3.0:
        # High: stronger correction (0.82-0.92)
        return 0.92 - 0.10 * (ratio - 2.0) / 1.0
    else:
        # Extreme: aggressive correction (0.75-0.82)
        ratio_scaled = min((ratio - 3.0) / 2.0, 1.0)
        return 0.82 - 0.07 * ratio_scaled
```

**Changes:**
- No correction for ratio < 1.15 (fixes balanced match underpricing)
- More aggressive for ratio > 2.0 (0.82 instead of 0.93)
- Very aggressive for ratio > 3.0 (0.75-0.82 instead of 0.90-0.92)

### Fix 2: Revised Favorite Correction Function

```python
def get_favorite_correction(ratio: float) -> float:
    """
    Revised favorite correction - scales with imbalance.
    """
    if ratio <= 1.15:
        return 1.0  # No correction for balanced
    elif ratio <= 2.0:
        # Slight correction (0.97-1.00)
        return 1.0 - 0.03 * (ratio - 1.15) / 0.85
    else:
        # Higher correction for extreme favorites (0.90-0.97)
        return 0.97 - 0.07 * min((ratio - 2.0) / 2.0, 1.0)
```

**Changes:**
- No correction for balanced matches
- Scales with ratio for high imbalances
- Favorites in extreme mismatches get 0.90-0.92 correction

### Fix 3: Remove Double Correction in Supremacy Optimization

**Current (lines 220-245):**
```python
def supremacy_loss(sup):
    l_home = (lambda_total + sup) / 2
    l_away = (lambda_total - sup) / 2
    # Apply empirical correction after supremacy adjustment  ❌ REMOVE THIS
    l_home_corr, l_away_corr = empirical_underdog_correction(l_home, l_away)
    # ... rest of calculation
```

**Fixed:**
```python
def supremacy_loss(sup):
    l_home = (lambda_total + sup) / 2
    l_away = (lambda_total - sup) / 2
    # Use raw lambdas - correction applied to probabilities later
    max_goals = 10
    # ... rest of calculation uses l_home, l_away directly
```

**Also remove lines 245 and 263** where `empirical_underdog_correction()` is called after supremacy calculation.

---

## 7. EXPECTED IMPROVEMENTS

After implementing these fixes:

| Metric | Before | After (Est.) | Improvement |
|--------|--------|--------------|-------------|
| Underdog MAE | 0.218 | ~0.12 | -45% |
| Favorite MAE | 0.077 | ~0.06 | -22% |
| Overall MAE | 0.147 | ~0.09 | -39% |
| Extreme Ratio MAE | 0.613 | ~0.25 | -59% |

---

## 8. IMPLEMENTATION PRIORITY

1. **HIGH PRIORITY:** Fix 1 (Underdog correction) - Biggest impact
2. **HIGH PRIORITY:** Fix 3 (Remove double correction) - Prevents over-correction
3. **MEDIUM PRIORITY:** Fix 2 (Favorite correction) - Fine-tuning

---

## 9. TESTING RECOMMENDATIONS

After implementing fixes:

1. Re-run analysis on same 117 matches
2. Compare error distribution by ratio bin
3. Verify balanced matches (ratio < 1.2) are no longer underpriced
4. Confirm extreme matches (ratio > 3.0) show <0.15 MAE
5. Run on new data to validate generalization

---

**Generated:** 2026-01-08
**Analyst:** Claude Sonnet 4.5
**Data Source:** reports/analysis_20260108_212226.csv
