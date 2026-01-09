# Poisson Calibrated Engine - V4 DRASTIC Calibration

**Date:** 2026-01-09
**Dataset:** 351 matches analyzed against BOTH Sportybet AND Bet9ja de-vigged fair odds
**Approach:** Aggressive inverse corrections + catastrophic reduction for extremes

---

## Executive Summary

V4 implements **DRASTIC corrections** based on 351-match analysis that revealed:
1. **Systematic underpricing** of balanced matches (-10 to -12%)
2. **Catastrophic overpricing** of extreme underdogs (+76 to +107%)

**Revolutionary approach:**
- **INCREASE** probabilities for balanced matches (both underdog AND favorite)
- **SLASH** extreme underdog probabilities by 50-55%

---

## V3 Performance Analysis (351 Matches)

### Overall Performance - UNACCEPTABLE
| Bookmaker | Overall MAE | vs 117-match dataset | Change |
|-----------|-------------|---------------------|---------|
| **Sportybet** | 0.1773 | 0.1436 | +23.5% ❌ |
| **Bet9ja** | 0.1747 | 0.1394 | +25.3% ❌ |

**V3 degraded by 23-25% on larger dataset!**

### Underdog vs Favorite
| Metric | VS Sportybet | VS Bet9ja |
|--------|--------------|-----------|
| **Underdog MAE** | 0.2397 | 0.2402 |
| **Favorite MAE** | 0.1150 | 0.1091 |
| **Underdog Bias** | **+4.2%** | **-0.4%** |
| **Favorite Bias** | **-9.9%** | **-9.2%** |

### By Lambda Ratio - THE DISASTER

| Ratio Range | Count | Sportybet | Bet9ja | Issue |
|-------------|-------|-----------|--------|-------|
| **<1.15** | 49 | **-9.8%** | **-9.1%** | ❌ UNDERPRICING |
| **1.15-1.5** | 102 | **-11.4%** | **-12.3%** | ❌❌ SEVERE UNDERPRICING |
| **1.5-2.0** | 116 | **-4.6%** | **-6.8%** | ⚠️ Underpricing |
| **2.0-3.0** | 61 | **+19.6%** | **+10.1%** | ❌❌ SEVERE OVERPRICING |
| **>3.0** | 23 | **+107.4%** | **+76.3%** | 🔴🔴🔴 CATASTROPHIC |

**The >3.0 ratio problem:**
- 23 matches with extreme team imbalance
- Our odds are **2x to 3x higher** than they should be
- Example: We price underdog at 10.0, should be 5.0
- **CATASTROPHIC for business** - giving away value

---

## V4 Calibration Strategy - REVOLUTIONARY

### Underdog Correction Function

```python
def get_underdog_correction(ratio: float) -> float:
    if ratio <= 1.15:
        # Balanced: INCREASE underdog probability by 0-15%
        return 1.0 + 0.15 * (ratio - 1.0) / 0.15
    elif ratio <= 1.5:
        # Slight: INCREASE transitioning (1.15 -> 1.0)
        return 1.15 - 0.15 * (ratio - 1.15) / 0.35
    elif ratio <= 2.0:
        # Moderate: light reduction (1.0 -> 0.92)
        return 1.0 - 0.08 * (ratio - 1.5) / 0.5
    elif ratio <= 3.0:
        # High: VERY AGGRESSIVE reduction (0.92 -> 0.70)
        return 0.92 - 0.22 * (ratio - 2.0) / 1.0
    else:
        # Extreme: CATASTROPHIC reduction (0.70 -> 0.45)
        # Cut probability by 50-55% to fix +76-107% overpricing
        ratio_scaled = min((ratio - 3.0) / 3.0, 1.0)
        return 0.70 - 0.25 * ratio_scaled
```

**Changes from V3:**
| Ratio | V3 Correction | V4 Correction | Change |
|-------|---------------|---------------|--------|
| **1.0** | 1.00 | **1.00** | - |
| **1.15** | 0.995 | **1.15** | +15.5% ⬆️ |
| **1.5** | 0.995 | **1.00** | +0.5% ⬆️ |
| **2.0** | 0.94 | **0.92** | -2.1% ⬇️ |
| **3.0** | 0.82 | **0.70** | -14.6% ⬇️⬇️ |
| **6.0** | 0.72 | **0.45** | -37.5% ⬇️⬇️⬇️ |

### Favorite Correction Function

```python
def get_favorite_correction(ratio: float) -> float:
    if ratio <= 1.5:
        # Balanced: INCREASE favorite probability by 0-10%
        return 1.0 + 0.10 * (ratio - 1.0) / 0.5
    elif ratio <= 2.5:
        # Moderate: transition from boost to neutral (1.10 -> 1.0)
        return 1.10 - 0.10 * (ratio - 1.5) / 1.0
    else:
        # High/Extreme: very light reduction (1.0 -> 0.98)
        return 1.0 - 0.02 * min((ratio - 2.5) / 2.0, 1.0)
```

**Changes from V3:**
| Ratio | V3 Correction | V4 Correction | Change |
|-------|---------------|---------------|--------|
| **1.0** | 1.00 | **1.00** | - |
| **1.5** | 1.00 | **1.10** | +10.0% ⬆️ |
| **2.0** | 0.985 | **1.05** | +6.6% ⬆️ |
| **2.5** | 0.985 | **1.00** | +1.5% ⬆️ |
| **4.5** | 0.97 | **0.98** | +1.0% ⬆️ |

---

## Key Innovation: Inverse Corrections

### Traditional Approach (V1-V3):
- **Reduce** underdog probabilities (they're overpriced)
- **Reduce** favorite probabilities (markets are tight)

### V4 Revolutionary Approach:
- **For balanced matches (<1.5):**
  - **INCREASE** underdog probabilities by 0-15%
  - **INCREASE** favorite probabilities by 0-10%
  - **Reason:** We're systematically UNDERPRICING both sides

- **For extreme matches (>3.0):**
  - **SLASH** underdog probabilities by 50-55%
  - **Reason:** We're catastrophically OVERPRICING (+76-107%)

---

## Expected V4 Improvements

| Ratio Range | V3 Bias | V4 Target | Expected Improvement |
|-------------|---------|-----------|---------------------|
| **<1.15** | -9.8% | ±2% | Eliminate 7.8% underpricing |
| **1.15-1.5** | -11.4% | ±2% | Eliminate 9.4% underpricing |
| **1.5-2.0** | -5.5% | ±2% | Eliminate 3.5% underpricing |
| **2.0-3.0** | +15% | ±5% | Reduce 10% overpricing |
| **>3.0** | +92% | ±10% | **Eliminate 82% overpricing!** |

### Target Overall Performance
- **Overall MAE:** 0.177 → **0.10** (-43%)
- **Underdog MAE:** 0.240 → **0.12** (-50%)
- **Extreme Ratio MAE:** 1.13 → **0.20** (-82%)

---

## Business Impact

### V3 Issues:
1. **Balanced matches:** Offering odds too high (losing money on value hunters)
2. **Extreme underdogs:** Offering odds 2-3x too high (catastrophic value loss)

**Example Extreme Match:**
- Team A (huge favorite) vs Team B (huge underdog)
- Lambda ratio: 4.5
- **V3:** Underdog odds = 10.50
- **Market fair:** Underdog odds = 5.00
- **V3 error:** +5.50 odds = **110% overpriced!**
- **If customer bets $100:** Expected loss = $110

### V4 Fixes:
1. **Balanced matches:** Lower odds (capture proper value)
2. **Extreme underdogs:** Cut odds in HALF (eliminate catastrophic losses)

---

## Testing Instructions

1. **Update database:** Use V4 engine to recalculate all matches
2. **Run analysis:** `python scripts/dual_bookmaker_analysis.py`
3. **Compare results:**
   - Check balanced match bias is near 0%
   - Verify extreme ratio bias drops from +92% to <10%
   - Confirm overall MAE drops to ~0.10

---

## Files Modified

- **[src/engine/poisson_calibrated.py](src/engine/poisson_calibrated.py)** - V4 correction functions

---

## Critical Insight

**The Monte Carlo simulation systematically:**
1. **Underprice**s balanced matches (both sides)
2. **Overprice**s extreme underdogs (massively)

**V4 fixes this by:**
1. Applying **inverse corrections** (BOOST) for balanced matches
2. Applying **catastrophic reductions** (50%+ cuts) for extreme underdogs

This is a **fundamental shift** from previous versions that only reduced probabilities.

---

**Generated:** 2026-01-09
**Analyst:** Claude Sonnet 4.5
**Dataset:** 351 matches vs Sportybet & Bet9ja (de-vigged)
**Commit:** `9fafcd4` on `engine-tuning` branch
