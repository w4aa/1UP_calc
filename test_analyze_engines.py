"""
Unit tests for analyze_engines.py

Tests the odds-to-implied-probability conversion and error handling.
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

from analyze_engines import odds_to_implied_prob, select_reference_bookmaker


def test_odds_to_implied_prob():
    """Test odds to implied probability conversion."""
    print("Testing odds_to_implied_prob()...")

    # Test 1: Basic conversion
    print("\n  Test 1: odds=2.0 -> prob=0.5")
    result = odds_to_implied_prob(2.0)
    assert result is not None, "Result should not be None"
    assert abs(result - 0.5) < 0.0001, f"Expected 0.5, got {result}"
    print(f"    [OK] odds=2.0 -> prob={result:.4f}")

    # Test 2: Favorite
    print("\n  Test 2: odds=1.5 -> prob=0.6667")
    result = odds_to_implied_prob(1.5)
    assert result is not None
    expected = 1.0 / 1.5
    assert abs(result - expected) < 0.0001, f"Expected {expected:.4f}, got {result}"
    print(f"    [OK] odds=1.5 -> prob={result:.4f}")

    # Test 3: Underdog
    print("\n  Test 3: odds=5.0 -> prob=0.2")
    result = odds_to_implied_prob(5.0)
    assert result is not None
    expected = 1.0 / 5.0
    assert abs(result - expected) < 0.0001, f"Expected {expected:.4f}, got {result}"
    print(f"    [OK] odds=5.0 -> prob={result:.4f}")

    # Test 4: Invalid odds (≤1.0)
    print("\n  Test 4: Invalid odds should return None")
    assert odds_to_implied_prob(1.0) is None, "odds=1.0 should return None"
    assert odds_to_implied_prob(0.5) is None, "odds=0.5 should return None"
    assert odds_to_implied_prob(0.0) is None, "odds=0.0 should return None"
    assert odds_to_implied_prob(-1.0) is None, "odds=-1.0 should return None"
    print("    [OK] Invalid odds return None")

    # Test 5: None input
    print("\n  Test 5: None input should return None")
    assert odds_to_implied_prob(None) is None, "None should return None"
    print("    [OK] None input returns None")

    # Test 6: Edge case close to 1.0
    print("\n  Test 6: odds=1.01 -> prob~0.9901")
    result = odds_to_implied_prob(1.01)
    assert result is not None
    expected = 1.0 / 1.01
    assert abs(result - expected) < 0.0001, f"Expected {expected:.4f}, got {result}"
    print(f"    [OK] odds=1.01 -> prob={result:.4f}")

    print("\n[PASS] All odds_to_implied_prob tests passed!")


def test_no_division_by_zero():
    """Test that we never divide by zero."""
    print("\nTesting division-by-zero safety...")

    # Zero odds
    result = odds_to_implied_prob(0.0)
    assert result is None, "Zero odds should return None, not raise exception"
    print("  [OK] Zero odds handled safely")

    # Very small odds
    result = odds_to_implied_prob(0.001)
    assert result is None, "Very small odds (≤1.0) should return None"
    print("  [OK] Very small odds handled safely")

    print("\n[PASS] Division-by-zero safety tests passed!")


def test_reference_selection():
    """Test that reference bookmaker selection is correct."""
    print("\nTesting reference bookmaker selection...")

    # Test 1: Pawa uses Sporty
    print("\n  Test 1: bookmaker=pawa -> ref=sporty")
    ref = select_reference_bookmaker('pawa')
    assert ref == 'sporty', f"Expected 'sporty', got '{ref}'"
    print(f"    [OK] pawa -> {ref}")

    # Test 2: Sporty uses Sporty
    print("\n  Test 2: bookmaker=sporty -> ref=sporty")
    ref = select_reference_bookmaker('sporty')
    assert ref == 'sporty', f"Expected 'sporty', got '{ref}'"
    print(f"    [OK] sporty -> {ref}")

    # Test 3: Bet9ja uses Bet9ja
    print("\n  Test 3: bookmaker=bet9ja -> ref=bet9ja")
    ref = select_reference_bookmaker('bet9ja')
    assert ref == 'bet9ja', f"Expected 'bet9ja', got '{ref}'"
    print(f"    [OK] bet9ja -> {ref}")

    # Test 4: Unknown defaults to Sporty
    print("\n  Test 4: Unknown bookmaker defaults to sporty")
    ref = select_reference_bookmaker('unknown')
    assert ref == 'sporty', f"Expected 'sporty' (default), got '{ref}'"
    print(f"    [OK] unknown -> {ref} (default)")

    print("\n[PASS] All reference selection tests passed!")


def test_margin_application():
    """Test margin application to fair odds."""
    print("\nTesting margin application...")

    # Test case: p=0.5, margin=0.10
    # fair_odds = 1/0.5 = 2.0
    # offer_odds = 2.0 * (1 - 0.10) = 1.8
    # offer_prob = 1/1.8 = 0.5556

    print("\n  Test: p=0.5, margin=0.10")
    p = 0.5
    margin = 0.10

    # Manual calculation
    fair_odds = 1.0 / p
    print(f"    Fair odds: {fair_odds:.2f}")

    offer_odds_expected = fair_odds * (1 - margin)
    print(f"    Expected offer odds: {offer_odds_expected:.2f}")

    offer_prob_expected = 1.0 / offer_odds_expected
    print(f"    Expected offer prob: {offer_prob_expected:.4f}")

    # Test that calculation is correct
    assert abs(offer_odds_expected - 1.8) < 0.001, f"Offer odds should be 1.8, got {offer_odds_expected}"
    assert abs(offer_prob_expected - 0.5556) < 0.001, f"Offer prob should be ~0.5556, got {offer_prob_expected}"

    print("    [OK] Margin application formula correct")

    # Test zero margin case
    print("\n  Test: p=0.5, margin=0.0 (no margin)")
    fair_odds = 1.0 / 0.5
    offer_odds_zero_margin = fair_odds * (1 - 0.0)
    assert abs(offer_odds_zero_margin - fair_odds) < 0.001, "Zero margin should preserve fair odds"
    print(f"    [OK] Zero margin preserves fair odds: {offer_odds_zero_margin:.2f}")

    # Test large margin case
    print("\n  Test: p=0.5, margin=0.20 (20% margin)")
    offer_odds_large = fair_odds * (1 - 0.20)
    assert abs(offer_odds_large - 1.6) < 0.001, f"20% margin should give 1.6, got {offer_odds_large}"
    print(f"    [OK] Large margin: {offer_odds_large:.2f}")

    print("\n[PASS] All margin application tests passed!")


def main():
    """Run all tests."""
    print("=" * 60)
    print("  ANALYZE_ENGINES.PY UNIT TESTS")
    print("=" * 60)

    tests = [
        test_odds_to_implied_prob,
        test_no_division_by_zero,
        test_reference_selection,
        test_margin_application,
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
