"""
Unit Tests for FTS-Calibrated-DP Engine

Tests the critical provider-aware FTS selection logic:
- Sporty → uses Sporty FTS
- Bet9ja → uses Bet9ja FTS
- Pawa → uses Sporty FTS (same provider)
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.engine import FTSCalibratedDPEngine


def test_provider_aware_fts_selection():
    """Test that engine correctly selects FTS source based on bookmaker."""
    print("Testing provider-aware FTS selection...")

    engine = FTSCalibratedDPEngine(n_sims=10000, match_minutes=95, margin_pct=0.0)

    # Prepare test markets with FTS from both providers
    markets = {
        '1x2': (2.10, 3.40, 3.20),
        'total_ou': (2.5, 1.85, 2.05),
        'btts': (1.75, 2.10),
        'first_goal': {
            'sporty': (2.50, 5.00, 3.20),  # Sporty FTS
            'bet9ja': (2.40, 5.20, 3.30),  # Bet9ja FTS (different)
        }
    }

    # Test 1: Sporty pricing uses Sporty FTS
    print("\n  Test 1: Sporty bookmaker")
    result_sporty = engine.calculate(markets, 'sporty')
    assert result_sporty is not None, "Sporty calculation failed"
    assert result_sporty['fts_source'] == 'sporty', f"Wrong FTS source: {result_sporty['fts_source']}"
    print(f"    [OK] FTS source: {result_sporty['fts_source']}")

    # Test 2: Bet9ja pricing uses Bet9ja FTS
    print("\n  Test 2: Bet9ja bookmaker")
    result_bet9ja = engine.calculate(markets, 'bet9ja')
    assert result_bet9ja is not None, "Bet9ja calculation failed"
    assert result_bet9ja['fts_source'] == 'bet9ja', f"Wrong FTS source: {result_bet9ja['fts_source']}"
    print(f"    [OK] FTS source: {result_bet9ja['fts_source']}")

    # Test 3: Pawa pricing uses Sporty FTS (CRITICAL)
    print("\n  Test 3: Pawa bookmaker (should use Sporty FTS)")
    result_pawa = engine.calculate(markets, 'pawa')
    assert result_pawa is not None, "Pawa calculation failed"
    assert result_pawa['fts_source'] == 'sporty_for_pawa', f"Wrong FTS source: {result_pawa['fts_source']}"
    print(f"    [OK] FTS source: {result_pawa['fts_source']}")

    # Test 4: Verify conditional shares are different for Sporty vs Bet9ja
    p_cond_sporty = result_sporty['p_cond_from_fts']
    p_cond_bet9ja = result_bet9ja['p_cond_from_fts']
    print(f"\n  Test 4: Conditional shares differ")
    print(f"    Sporty p_cond: {p_cond_sporty:.4f}")
    print(f"    Bet9ja p_cond: {p_cond_bet9ja:.4f}")
    assert abs(p_cond_sporty - p_cond_bet9ja) > 0.001, "Sporty and Bet9ja should have different p_cond"
    print(f"    [OK] Difference: {abs(p_cond_sporty - p_cond_bet9ja):.4f}")

    # Test 5: Verify Pawa uses same p_cond as Sporty
    p_cond_pawa = result_pawa['p_cond_from_fts']
    print(f"\n  Test 5: Pawa uses Sporty FTS values")
    print(f"    Pawa p_cond: {p_cond_pawa:.4f}")
    print(f"    Sporty p_cond: {p_cond_sporty:.4f}")
    assert abs(p_cond_pawa - p_cond_sporty) < 0.0001, "Pawa should use Sporty FTS"
    print(f"    [OK] Match confirmed (diff: {abs(p_cond_pawa - p_cond_sporty):.6f})")

    print("\n[PASS] All provider-aware tests passed!")


def test_probability_bounds():
    """Test that calculated probabilities are valid."""
    print("\nTesting probability bounds...")

    engine = FTSCalibratedDPEngine()

    markets = {
        '1x2': (2.10, 3.40, 3.20),
        'total_ou': (2.5, 1.85, 2.05),
        'btts': (1.75, 2.10),
        'first_goal': {
            'sporty': (2.50, 5.00, 3.20),
            'bet9ja': (2.40, 5.20, 3.30),
        }
    }

    for bookmaker in ['sporty', 'pawa', 'bet9ja']:
        print(f"\n  Testing {bookmaker}...")
        result = engine.calculate(markets, bookmaker)

        assert result is not None, f"{bookmaker} calculation failed"

        # Check probability bounds
        p_home = result['p_home_1up']
        p_away = result['p_away_1up']

        assert 0 < p_home < 1, f"Invalid p_home_1up: {p_home}"
        assert 0 < p_away < 1, f"Invalid p_away_1up: {p_away}"

        # Check odds are reasonable
        fair_home = result['1up_home_fair']
        fair_away = result['1up_away_fair']

        assert fair_home >= 1.0, f"Invalid fair_home: {fair_home}"
        assert fair_away >= 1.0, f"Invalid fair_away: {fair_away}"

        print(f"    [OK] p_home_1up: {p_home:.4f} (odds: {fair_home:.2f})")
        print(f"    [OK] p_away_1up: {p_away:.4f} (odds: {fair_away:.2f})")

    print("\n[PASS] All probability bounds valid!")


def test_fallback_to_1x2():
    """Test fallback when no FTS data available."""
    print("\nTesting fallback to 1X2 when FTS missing...")

    engine = FTSCalibratedDPEngine()

    markets_no_fts = {
        '1x2': (2.10, 3.40, 3.20),
        'total_ou': (2.5, 1.85, 2.05),
        'btts': (1.75, 2.10),
        'first_goal': None,  # No FTS data
    }

    result = engine.calculate(markets_no_fts, 'sporty')
    assert result is not None, "Should work without FTS"
    assert 'none_fallback_to_1x2' in result['fts_source'], f"Wrong fallback: {result['fts_source']}"

    print(f"  [OK] FTS source: {result['fts_source']}")
    print(f"  [OK] Fallback p_cond: {result['p_cond_from_fts']:.4f}")

    print("\n[PASS] Fallback test passed!")


def test_calibration_applied():
    """Test that post-FTS calibration is applied."""
    print("\nTesting calibration...")

    engine = FTSCalibratedDPEngine()

    markets = {
        '1x2': (2.10, 3.40, 3.20),
        'total_ou': (2.5, 1.85, 2.05),
        'btts': (1.75, 2.10),
        'first_goal': {
            'sporty': (2.50, 5.00, 3.20),
            'bet9ja': None,
        }
    }

    result = engine.calculate(markets, 'sporty')
    assert result is not None

    # Check that raw and calibrated probs are different
    p_home_raw = result['p_home_1up_raw']
    p_home_adj = result['p_home_1up']

    print(f"  Raw p_home_1up: {p_home_raw:.4f}")
    print(f"  Calibrated p_home_1up: {p_home_adj:.4f}")
    print(f"  Adjustment: {((p_home_adj - p_home_raw) / p_home_raw * 100):.2f}%")

    # Calibration should change the probability
    assert abs(p_home_raw - p_home_adj) > 0.001, "Calibration should modify probabilities"

    print("\n[PASS] Calibration applied!")


def test_dp_barrier_correctness():
    """Test the absorbing-barrier DP implementation."""
    print("\nTesting DP barrier calculation correctness...")

    engine = FTSCalibratedDPEngine()

    # Test 1: n=1 case
    print("\n  Test 1: n=1 (single goal)")
    n = 1
    p = 0.6

    # For n=1: if home scores, hit +1 (prob=p); if away scores, hit -1 (prob=1-p)
    prob_plus1 = engine._prob_hit_barrier(n, p, +1)
    prob_minus1 = engine._prob_hit_barrier(n, p, -1)

    print(f"    P(hit +1 | n=1, p={p}): {prob_plus1:.4f} (expected: {p:.4f})")
    print(f"    P(hit -1 | n=1, p={p}): {prob_minus1:.4f} (expected: {1-p:.4f})")

    assert abs(prob_plus1 - p) < 0.001, f"n=1: prob_hit(+1) should equal p={p}, got {prob_plus1}"
    assert abs(prob_minus1 - (1-p)) < 0.001, f"n=1: prob_hit(-1) should equal 1-p={1-p}, got {prob_minus1}"
    print("    OK: n=1 case correct")

    # Test 2: n=2, p=0.5 case
    print("\n  Test 2: n=2, p=0.5")
    n = 2
    p = 0.5

    # For n=2, p=0.5: paths are HH, HA, AH, AA
    # HH: 0 -> +1 -> +2 (hits +1)
    # HA: 0 -> +1 -> 0 (hits +1)
    # AH: 0 -> -1 -> 0 (hits -1)
    # AA: 0 -> -1 -> -2 (hits -1)
    # So P(hit +1) = 0.5 (HH or HA) = 0.5, P(hit -1) = 0.5 (AH or AA) = 0.5
    # Wait, that's wrong. Let me recalculate:
    # Each path has probability 0.25
    # HH: hits +1 at step 1
    # HA: hits +1 at step 1, then returns (but already hit)
    # AH: hits -1 at step 1, then returns (but already hit)
    # AA: hits -1 at step 1
    # P(ever hit +1) = P(HH) + P(HA) = 0.25 + 0.25 = 0.5
    # P(ever hit -1) = P(AH) + P(AA) = 0.25 + 0.25 = 0.5
    # Actually both should be 0.5 for p=0.5 by symmetry

    prob_plus1 = engine._prob_hit_barrier(n, p, +1)
    prob_minus1 = engine._prob_hit_barrier(n, p, -1)

    print(f"    P(hit +1 | n=2, p=0.5): {prob_plus1:.4f} (expected: 0.5000)")
    print(f"    P(hit -1 | n=2, p=0.5): {prob_minus1:.4f} (expected: 0.5000)")

    assert abs(prob_plus1 - 0.5) < 0.001, f"n=2, p=0.5: prob_hit(+1) should be 0.5, got {prob_plus1}"
    assert abs(prob_minus1 - 0.5) < 0.001, f"n=2, p=0.5: prob_hit(-1) should be 0.5, got {prob_minus1}"
    print("    OK: n=2, p=0.5 case correct")

    # Test 3: Symmetry
    print("\n  Test 3: Symmetry")
    n = 3
    p = 0.7

    prob_plus1_p = engine._prob_hit_barrier(n, p, +1)
    prob_minus1_1minusp = engine._prob_hit_barrier(n, 1-p, -1)

    print(f"    P(hit +1 | n=3, p=0.7): {prob_plus1_p:.4f}")
    print(f"    P(hit -1 | n=3, p=0.3): {prob_minus1_1minusp:.4f}")
    print(f"    Symmetry check: {abs(prob_plus1_p - prob_minus1_1minusp):.6f}")

    # By symmetry: P(hit +1 with p) = P(hit -1 with 1-p)
    assert abs(prob_plus1_p - prob_minus1_1minusp) < 0.001, "Symmetry violated"
    print("    OK: Symmetry holds")

    # Test 4: Monotonicity (higher p -> higher prob of hitting +1)
    print("\n  Test 4: Monotonicity")
    n = 4

    prob_p03 = engine._prob_hit_barrier(n, 0.3, +1)
    prob_p05 = engine._prob_hit_barrier(n, 0.5, +1)
    prob_p07 = engine._prob_hit_barrier(n, 0.7, +1)

    print(f"    P(hit +1 | n=4, p=0.3): {prob_p03:.4f}")
    print(f"    P(hit +1 | n=4, p=0.5): {prob_p05:.4f}")
    print(f"    P(hit +1 | n=4, p=0.7): {prob_p07:.4f}")

    assert prob_p03 < prob_p05 < prob_p07, "Monotonicity violated: higher p should give higher prob_hit(+1)"
    print("    OK: Monotonicity holds")

    print("\n[PASS] All DP barrier tests passed!")


def main():
    """Run all tests."""
    print("=" * 60)
    print("  FTS-CALIBRATED-DP ENGINE UNIT TESTS")
    print("=" * 60)

    tests = [
        test_provider_aware_fts_selection,
        test_probability_bounds,
        test_fallback_to_1x2,
        test_calibration_applied,
        test_dp_barrier_correctness,
    ]

    for test_func in tests:
        try:
            test_func()
        except AssertionError as e:
            print(f"\n[FAIL] {test_func.__name__}: {e}")
            return 1
        except Exception as e:
            print(f"\n[ERROR] {test_func.__name__}: {e}")
            import traceback
            traceback.print_exc()
            return 1

    print("\n" + "=" * 60)
    print("  ALL TESTS PASSED!")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
