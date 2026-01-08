# Poisson Calibrated Engine - Calibration Results

**Date:** 2026-01-08
**Test Dataset:** 117 matches (pawa bookmaker)

## Summary

Successfully fixed the **double correction bug** and refined calibration factors. Results show significant improvement in underdog pricing accuracy, though some areas need further tuning.

---

## ✅ Major Wins

### 1. Underdog Bias Elimination (-95%)
- **Before:** +0.0883 (significant overpricing)
- **After:** +0.0044 (near-perfect)
- **Improvement:** -95.0%

This was the PRIMARY goal - eliminate systematic underdog overpricing. ✅ **ACHIEVED**

### 2. Away Side Error Reduction (-14.3%)
- **Before:** 0.1918 MAE
- **After:** 0.1643 MAE
- **Improvement:** -14.3%

### 3. Underdog MAE Improvement (-19.3%)
- **Before:** 0.2175
- **After:** 0.1755
- **Improvement:** -19.3%

### 4. High Imbalance Matches (Ratio 2.0-3.0) - BEST
- **Underdog MAE:** 0.4527 → 0.2266 (-49.9%) 🎯
- **Underdog Bias:** +0.2139 → +0.1713 (reduced overpricing)

This was the second-worst category. Major improvement!

---

## ⚠️ Areas Needing Adjustment

### 1. Favorite Side Overcorrection (+34%)
- **Before:** 0.0767 MAE
- **After:** 0.1027 MAE
- **Issue:** Favorites now slightly underpriced

**Root Cause:** Favorite correction function may be too aggressive for lower ratios.

### 2. Balanced/Slight Imbalance (Ratio < 1.5)
- **Underdog MAE:** Increased by 7-41%
- **Favorite MAE:** Increased by 35-48%
- **Issue:** Now UNDERPRICING both sides in balanced matches

**Root Cause:** Removed lambda-level correction changed base probabilities. Thresholds need recalibration.

### 3. Extreme Mismatches (Ratio > 3.0) - STILL PROBLEMATIC
- **Underdog MAE:** 0.6744 → 0.7308 (+8.4%) ❌
- **Still the worst category** despite aggressive correction

**Root Cause:** Even 0.75-0.82 correction is insufficient for extreme ratios.

---

## 🔧 Technical Changes

### Double Correction Bug - FIXED ✅
**Before:**
1. Lambda correction applied in supremacy optimization
2. Probability correction applied after simulation
3. Result: Over-correction, wrong lambdas

**After:**
1. Raw lambdas used in supremacy optimization
2. Probability correction applied ONLY to 1UP probabilities
3. Result: Correct lambdas, single correction point

**Impact:**
- Lambdas changed (correct now)
- Base probabilities changed
- Correction thresholds need adjustment for new baseline

---

## 📊 Detailed Metrics Comparison

| Metric | Before | After | Change | % Change |
|--------|--------|-------|--------|----------|
| **Home MAE** | 0.1023 | 0.1139 | +0.0116 | +11.3% |
| **Away MAE** | 0.1918 | 0.1643 | -0.0275 | -14.3% ✅ |
| **Home Bias** | -0.0034 | -0.0710 | -0.0675 | -1970% |
| **Away Bias** | +0.0443 | -0.0121 | -0.0564 | -127% ✅ |
| **Underdog MAE** | 0.2175 | 0.1755 | -0.0420 | -19.3% ✅ |
| **Favorite MAE** | 0.0767 | 0.1027 | +0.0261 | +34.0% ⚠️ |
| **Underdog Bias** | +0.0883 | +0.0044 | -0.0839 | -95.0% ✅✅ |
| **Favorite Bias** | -0.0474 | -0.0875 | -0.0401 | +84.5% ⚠️ |

### By Lambda Ratio

| Range | Underdog MAE Change | Favorite MAE Change |
|-------|---------------------|---------------------|
| **Balanced <1.15** (14 matches) | +7.7% ⚠️ | +48.1% ⚠️ |
| **Slight 1.15-1.5** (36 matches) | +41.4% ❌ | +35.4% ⚠️ |
| **Moderate 1.5-2.0** (35 matches) | -16.6% ✅ | +35.3% ⚠️ |
| **High 2.0-3.0** (24 matches) | -49.9% ✅✅ | +20.6% |
| **Extreme >3.0** (8 matches) | +8.4% ❌ | -23.0% ✅ |

---

## 🎯 Next Steps

### Priority 1: Fix Balanced/Slight Imbalance Underpricing
**Problem:** Ratio 1.0-1.5 now underpriced on both sides
**Solution:** Lower threshold, gentler correction for ratio < 1.5

**Proposed Fix:**
```python
if ratio <= 1.10:
    return 1.0  # Very balanced - no correction
elif ratio <= 1.3:
    return 0.995 - 0.015 * (ratio - 1.10) / 0.20  # Light correction
elif ratio <= 1.6:
    return 0.98 - 0.04 * (ratio - 1.3) / 0.30  # Standard
# ... rest unchanged
```

### Priority 2: Tune Favorite Correction
**Problem:** Favorites now underpriced across all ratios
**Solution:** Reduce favorite correction strength by ~30%

**Proposed Fix:**
```python
if ratio <= 1.15:
    return 1.0
elif ratio <= 2.0:
    return 1.0 - 0.02 * (ratio - 1.15) / 0.85  # Was 0.03
else:
    return 0.98 - 0.05 * min((ratio - 2.0) / 2.0, 1.0)  # Was 0.07
```

### Priority 3: More Aggressive Extreme Ratio Correction
**Problem:** Ratio > 3.0 still has massive errors
**Solution:** Increase correction to 0.70-0.75 range

---

## ✅ Verdict

**PARTIAL SUCCESS**

✅ **Major Win:** Underdog bias eliminated (-95%)
✅ **Major Win:** High imbalance errors cut in half (-50%)
⚠️ **Trade-off:** Balanced matches now need tuning
❌ **Still Broken:** Extreme mismatches (>3.0 ratio)

**Recommendation:**
1. Commit current version (bug fix is critical)
2. Create v2 with refined thresholds
3. Test on new data to validate

---

## 📝 Files

- **Before:** `reports/analysis_20260108_212226.csv`
- **After:** `reports/analysis_improved_20260108_213528.csv`
- **Code:** `src/engine/poisson_calibrated.py`
- **Analysis:** `ENGINE_ANALYSIS.md`

**Generated:** 2026-01-08 21:40
**Analyst:** Claude Sonnet 4.5
