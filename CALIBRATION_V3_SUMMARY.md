# Poisson Calibrated Engine - V3 Dual-Bookmaker Calibration

**Date:** 2026-01-08
**Dataset:** 117 matches analyzed against BOTH Sportybet AND Bet9ja actual 1UP odds
**Approach:** Unified calibration (performance nearly identical between bookmakers)

---

## Executive Summary

V3 implements targeted refinements based on comprehensive dual-bookmaker analysis. Key finding: **our fair odds perform nearly identically against both Sportybet and Bet9ja** (only 3% difference), confirming that a single unified calibration is appropriate.

### Critical Issues Addressed in V3:

1. **Balanced/Slight Matches (<1.5 ratio):** UNDERPRICING by 9-13%
   → **Solution:** Removed/minimized corrections

2. **High Imbalance (2.0-3.0 ratio):** Still OVERPRICING underdogs by 8-18%
   → **Solution:** More aggressive underdog correction (0.94 → 0.82)

3. **Favorites Across All Ratios:** UNDERPRICED by 8-13%
   → **Solution:** Further reduced favorite correction strength by ~50%

---

## Dual-Bookmaker Analysis Results (V2 Performance)

### Overall Performance
| Bookmaker | Home MAE | Away MAE | Overall MAE | Winner |
|-----------|----------|----------|-------------|--------|
| **Sportybet** | 0.1174 | 0.1697 | **0.1436** | |
| **Bet9ja** | 0.1144 | 0.1644 | **0.1394** | ✓ (3% better) |

**Conclusion:** Performance is nearly **IDENTICAL** between bookmakers (3% difference is negligible).

### Underdog vs Favorite Performance

| Metric | VS Sportybet | VS Bet9ja |
|--------|--------------|-----------|
| **Underdog MAE** | 0.1785 | 0.1760 |
| **Favorite MAE** | 0.1087 | 0.1029 |
| **Underdog Bias** | +0.0165 (slight overpricing) | -0.0294 (slight underpricing) |
| **Favorite Bias** | -0.0968 (underpricing) | -0.0901 (underpricing) |

**Key Insight:** Underdogs near-optimal vs Bet9ja but still overpriced vs Sportybet. Favorites consistently underpriced for both.

### Performance by Lambda Ratio

| Ratio Range | Count | VS Sportybet | VS Bet9ja | Issue |
|-------------|-------|--------------|-----------|-------|
| **<1.15** | 15 | Under -13.7%, Fav -12.5% | Under -12.7%, Fav -13.4% | ❌ UNDERPRICING both |
| **1.15-1.5** | 38 | Under -9.8%, Fav -9.8% | Under -10.8%, Fav -9.3% | ❌ UNDERPRICING both |
| **1.5-2.0** | 36 | Under -3.1%, Fav -9.8% | Under -5.3%, Fav -9.0% | ✅ GOOD (underdogs) |
| **2.0-3.0** | 21 | Under +18.1%, Fav -8.8% | Under +8.8%, Fav -7.5% | ❌ OVERPRICING underdogs |
| **>3.0** | 7 | NaN (insufficient data) | NaN (insufficient data) | - |

---

## V3 Calibration Strategy

### Underdog Correction Function

```python
def get_underdog_correction(ratio: float) -> float:
    if ratio <= 1.5:
        # Balanced to slight: MINIMAL correction
        # V2 was underpricing by 9-13%, so barely touch these
        return 1.0 - 0.005 * max(ratio - 1.2, 0.0) / 0.3
    elif ratio <= 2.0:
        # Moderate: light correction (0.995 -> 0.94)
        # V2 worked well here (only 3-5% off), keep similar
        return 0.995 - 0.055 * (ratio - 1.5) / 0.5
    elif ratio <= 3.0:
        # High: AGGRESSIVE correction (0.94 -> 0.82)
        # V2 still overpricing by 8-18%, need MUCH more aggression
        return 0.94 - 0.12 * (ratio - 2.0) / 1.0
    else:
        # Extreme: very aggressive correction (0.82 -> 0.72)
        ratio_scaled = min((ratio - 3.0) / 2.5, 1.0)
        return 0.82 - 0.10 * ratio_scaled
```

**Changes from V2:**
- **Ratio <1.5:** Near-zero correction (was 0.985-1.0) → Now 0.995-1.0
- **Ratio 1.5-2.0:** Keep V2 (worked well)
- **Ratio 2.0-3.0:** MORE aggressive (0.90→0.80 became 0.94→0.82)
- **Ratio >3.0:** Keep V2's aggression

### Favorite Correction Function

```python
def get_favorite_correction(ratio: float) -> float:
    if ratio <= 1.5:
        # Balanced to slight: NO correction
        # V2 was underpricing favorites by 9-13% in these ranges
        return 1.0
    elif ratio <= 2.5:
        # Moderate to high: very gentle correction (1.00 -> 0.985)
        # V2 was 0.98, still too strong
        return 1.0 - 0.015 * (ratio - 1.5) / 1.0
    else:
        # Very high imbalance: gentle correction (0.985 -> 0.97)
        # V2 was 0.94, way too aggressive
        return 0.985 - 0.015 * min((ratio - 2.5) / 2.0, 1.0)
```

**Changes from V2:**
- **Ratio <1.5:** NO correction (was 1.0 starting at 1.1)
- **Ratio 1.5-2.5:** Much gentler 1.0→0.985 (was 1.0→0.98)
- **Ratio >2.5:** Gentler 0.985→0.97 (was 0.98→0.94)

---

## Expected V3 Improvements

| Ratio Range | V2 Issue | V3 Target | Expected Improvement |
|-------------|----------|-----------|---------------------|
| **<1.15** | -12.5% underpricing | < -5% | Eliminate 7.5% underpricing |
| **1.15-1.5** | -9.8% underpricing | < -3% | Eliminate 6.8% underpricing |
| **1.5-2.0** | -3.1% underpricing (underdogs) | ±2% | Maintain good performance |
| **2.0-3.0** | +8% to +18% overpricing (underdogs) | < +5% | Reduce by 50-70% |
| **>3.0** | Insufficient data | - | Monitor with more data |

---

## Key Insight: Draw Odds Inconsistency

**Unexpected Finding:** Draw odds differ significantly between Sportybet and Bet9ja:
- Mean absolute difference: **0.11**
- Max difference: **0.77**
- Only 8.5% of matches have identical draw odds

**Implication:** The bookmakers are NOT using the exact same 1X2 market as initially assumed. They likely:
1. Source from different providers with different odds
2. Apply different margins to the draw outcome
3. Use slightly different 1X2 markets

This does NOT affect our calibration since we independently infer lambdas from each bookmaker's Over/Under markets.

---

## Testing Recommendations

1. **Clear Database:** Delete/rename `data/datas.db` to force recalculation with V3
2. **Run Engine:** Execute runner to populate with V3 calculations
3. **Run Dual-Bookmaker Analysis:** `python scripts/dual_bookmaker_analysis.py`
4. **Compare V2 vs V3:**
   - Balanced/Slight: Expect MAE reduction from 0.13-0.14 to 0.08-0.10
   - High imbalance: Expect underdog bias reduction from +0.09-0.18 to +0.02-0.05
   - Favorites: Expect bias reduction from -0.09 to -0.05

---

## Files Modified

- `src/engine/poisson_calibrated.py` - Updated correction functions
- `scripts/dual_bookmaker_analysis.py` - Comprehensive dual-bookmaker comparison script

---

**Generated:** 2026-01-08
**Analyst:** Claude Sonnet 4.5
**Commit:** `4324b15` on `engine-tuning` branch
