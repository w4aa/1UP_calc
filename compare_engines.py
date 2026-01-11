"""
Engine Comparison Script

Compares engine 1UP output vs actual bookmaker 1UP odds.
Shows MAE, max error, and error by lambda bins.

Clearly labels when PAWA odds were priced using Sporty FTS.
"""

import sys
from pathlib import Path
import sqlite3

PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.config import ConfigLoader
from src.db.manager import DatabaseManager


def get_engine_results(db: DatabaseManager, engine_name: str):
    """Get all engine calculations for analysis."""
    cursor = db.conn.cursor()

    query = """
    SELECT
        c.engine_name,
        c.bookmaker,
        c.lambda_total,
        c.p_home_1up,
        c.p_away_1up,
        c.fair_home,
        c.fair_away,
        c.actual_sporty_home,
        c.actual_sporty_away,
        c.actual_bet9ja_home,
        c.actual_bet9ja_away,
        e.home_team,
        e.away_team
    FROM engine_calculations c
    JOIN events e ON c.sportradar_id = e.sportradar_id
    WHERE c.engine_name = ?
    ORDER BY c.id DESC
    """

    cursor.execute(query, (engine_name,))
    return cursor.fetchall()


def compute_mae(calculated_odds, actual_odds_list):
    """
    Compute MAE between calculated odds and actual odds.

    Args:
        calculated_odds: Single calculated odd value
        actual_odds_list: List of actual odds (may contain None)

    Returns:
        Mean absolute error (on odds scale)
    """
    errors = []
    for actual in actual_odds_list:
        if actual and actual > 1.0:
            errors.append(abs(calculated_odds - actual))

    if not errors:
        return None

    return sum(errors) / len(errors)


def compute_prob_mae(calculated_prob, actual_odds_list):
    """
    Compute MAE on probability scale.

    Args:
        calculated_prob: Calculated probability
        actual_odds_list: List of actual odds (may contain None)

    Returns:
        Mean absolute error (on probability scale)
    """
    errors = []
    for actual_odds in actual_odds_list:
        if actual_odds and actual_odds > 1.0:
            actual_prob = 1.0 / actual_odds
            errors.append(abs(calculated_prob - actual_prob))

    if not errors:
        return None

    return sum(errors) / len(errors)


def analyze_engine(db: DatabaseManager, engine_name: str):
    """Analyze one engine's performance."""
    print(f"\n{'='*70}")
    print(f"  ENGINE: {engine_name}")
    print(f"{'='*70}")

    results = get_engine_results(db, engine_name)

    if not results:
        print("  No results found for this engine.")
        return

    print(f"  Total calculations: {len(results)}")

    # Group by bookmaker
    by_bookmaker = {}
    for row in results:
        bookmaker = row['bookmaker']
        if bookmaker not in by_bookmaker:
            by_bookmaker[bookmaker] = []
        by_bookmaker[bookmaker].append(row)

    for bookmaker in sorted(by_bookmaker.keys()):
        rows = by_bookmaker[bookmaker]
        print(f"\n  --- {bookmaker.upper()} ({len(rows)} calculations) ---")

        # Determine FTS source labeling
        if bookmaker == 'pawa' and engine_name == 'FTS-Calibrated-DP':
            print("  [Note: Pawa pricing uses Sporty FTS (same odds provider)]")

        # Collect errors
        home_errors_prob = []
        home_errors_odds = []
        away_errors_prob = []
        away_errors_odds = []
        lambda_totals_home = []
        lambda_totals_away = []

        for row in rows:
            # Get actual odds based on bookmaker
            if bookmaker == 'sporty':
                actual_home = row['actual_sporty_home']
                actual_away = row['actual_sporty_away']
            elif bookmaker == 'bet9ja':
                actual_home = row['actual_bet9ja_home']
                actual_away = row['actual_bet9ja_away']
            elif bookmaker == 'pawa':
                # Pawa doesn't have actual 1UP odds in most cases
                # But we can compare against Sporty (same provider)
                actual_home = row['actual_sporty_home']
                actual_away = row['actual_sporty_away']
            else:
                actual_home = None
                actual_away = None

            # Home errors
            if actual_home and actual_home > 1.0:
                calc_home = row['fair_home']
                prob_calc = row['p_home_1up']
                prob_actual = 1.0 / actual_home

                home_errors_prob.append(abs(prob_calc - prob_actual))
                home_errors_odds.append(abs(calc_home - actual_home))
                lambda_totals_home.append(row['lambda_total'])

            # Away errors
            if actual_away and actual_away > 1.0:
                calc_away = row['fair_away']
                prob_calc = row['p_away_1up']
                prob_actual = 1.0 / actual_away

                away_errors_prob.append(abs(prob_calc - prob_actual))
                away_errors_odds.append(abs(calc_away - actual_away))
                lambda_totals_away.append(row['lambda_total'])

        if home_errors_prob:
            print(f"\n  Home 1UP:")
            print(f"    MAE (probability): {sum(home_errors_prob)/len(home_errors_prob):.4f}")
            print(f"    MAE (odds): {sum(home_errors_odds)/len(home_errors_odds):.4f}")
            print(f"    Max error (odds): {max(home_errors_odds):.4f}")

        if away_errors_prob:
            print(f"\n  Away 1UP:")
            print(f"    MAE (probability): {sum(away_errors_prob)/len(away_errors_prob):.4f}")
            print(f"    MAE (odds): {sum(away_errors_odds)/len(away_errors_odds):.4f}")
            print(f"    Max error (odds): {max(away_errors_odds):.4f}")

        # Error by lambda bins for HOME
        if lambda_totals_home and home_errors_odds:
            print(f"\n  Home error by lambda_total bins:")

            bins = [(0, 2.0), (2.0, 2.5), (2.5, 3.0), (3.0, 5.0)]
            for low, high in bins:
                bin_errors_prob = [
                    e for e, lam in zip(home_errors_prob, lambda_totals_home)
                    if low <= lam < high
                ]
                bin_errors_odds = [
                    e for e, lam in zip(home_errors_odds, lambda_totals_home)
                    if low <= lam < high
                ]
                if bin_errors_odds:
                    print(f"    [{low:.1f}, {high:.1f}): MAE prob={sum(bin_errors_prob)/len(bin_errors_prob):.4f}, odds={sum(bin_errors_odds)/len(bin_errors_odds):.4f} (n={len(bin_errors_odds)})")

        # Error by lambda bins for AWAY
        if lambda_totals_away and away_errors_odds:
            print(f"\n  Away error by lambda_total bins:")

            bins = [(0, 2.0), (2.0, 2.5), (2.5, 3.0), (3.0, 5.0)]
            for low, high in bins:
                bin_errors_prob = [
                    e for e, lam in zip(away_errors_prob, lambda_totals_away)
                    if low <= lam < high
                ]
                bin_errors_odds = [
                    e for e, lam in zip(away_errors_odds, lambda_totals_away)
                    if low <= lam < high
                ]
                if bin_errors_odds:
                    print(f"    [{low:.1f}, {high:.1f}): MAE prob={sum(bin_errors_prob)/len(bin_errors_prob):.4f}, odds={sum(bin_errors_odds)/len(bin_errors_odds):.4f} (n={len(bin_errors_odds)})")

        if not home_errors_prob and not away_errors_prob:
            print("  [No actual 1UP odds available for comparison]")


def compare_engines_side_by_side(db: DatabaseManager):
    """Compare both engines side by side on same events."""
    print(f"\n{'='*70}")
    print(f"  SIDE-BY-SIDE COMPARISON")
    print(f"{'='*70}")

    cursor = db.conn.cursor()

    query = """
    SELECT
        c1.sportradar_id,
        c1.bookmaker,
        c1.fair_home as old_fair_home,
        c1.fair_away as old_fair_away,
        c2.fair_home as new_fair_home,
        c2.fair_away as new_fair_away,
        c1.actual_sporty_home,
        c1.actual_sporty_away,
        c1.actual_bet9ja_home,
        c1.actual_bet9ja_away,
        e.home_team,
        e.away_team
    FROM engine_calculations c1
    JOIN engine_calculations c2
        ON c1.sportradar_id = c2.sportradar_id
        AND c1.bookmaker = c2.bookmaker
    JOIN events e ON c1.sportradar_id = e.sportradar_id
    WHERE c1.engine_name = 'Poisson-Calibrated'
      AND c2.engine_name = 'FTS-Calibrated-DP'
    LIMIT 10
    """

    cursor.execute(query)
    rows = cursor.fetchall()

    if not rows:
        print("  No paired calculations found yet.")
        return

    print(f"\n  Sample: {len(rows)} matches")
    print(f"\n  {'Match':<35} {'Bookie':<6} {'Old':<8} {'New':<8} {'Actual':<8} {'Improvement'}")
    print("  " + "-" * 80)

    for row in rows:
        match = f"{row['home_team'][:15]} v {row['away_team'][:15]}"
        bookie = row['bookmaker'][:5]

        # Get actual
        if bookie == 'sporty':
            actual = row['actual_sporty_home']
        elif bookie == 'bet9j':
            actual = row['actual_bet9ja_home']
        else:
            actual = row['actual_sporty_home']  # Pawa uses Sporty

        if actual and actual > 1.0:
            old_fair = row['old_fair_home']
            new_fair = row['new_fair_home']

            old_error = abs(old_fair - actual)
            new_error = abs(new_fair - actual)

            improvement = old_error - new_error

            print(f"  {match:<35} {bookie:<6} {old_fair:>6.2f}  {new_fair:>6.2f}  {actual:>6.2f}  {improvement:+.3f}")


def main():
    """Run comparison analysis."""
    print("="*70)
    print("  ENGINE COMPARISON ANALYSIS")
    print("="*70)

    config = ConfigLoader()
    db = DatabaseManager(config.get_db_path())
    db.connect()

    try:
        # Analyze each engine
        analyze_engine(db, "Poisson-Calibrated")
        analyze_engine(db, "FTS-Calibrated-DP")

        # Side-by-side comparison
        compare_engines_side_by_side(db)

    finally:
        db.close()

    print("\n" + "="*70)
    print("  ANALYSIS COMPLETE")
    print("="*70)


if __name__ == "__main__":
    main()
