"""
1UP Engine Analysis Script

Analyzes engine calculation results stored in the database.
For each event/engine:
- Select correct REFERENCE bookmaker odds based on calculation bookmaker
- Compare engine fair probabilities with reference IMPLIED probabilities
- Report MAE in probability space (primary KPI)

IMPORTANT:
1. 1UP is NOT a complementary market (Home1UP and Away1UP can both happen)
2. Reference odds selection:
   - For pawa/sporty calculations → use Sporty odds as reference
   - For bet9ja calculations → use Bet9ja odds as reference
3. All errors computed vs REFERENCE odds only

Usage:
    python analyze_engines.py                            # Full analysis
    python analyze_engines.py --engine FTS-Calibrated-DP # Specific engine
    python analyze_engines.py --bookmaker pawa           # Specific bookmaker
    python analyze_engines.py --output reports           # Custom output folder
"""

import argparse
import csv
import logging
import sys
from datetime import datetime
import json
from pathlib import Path
from typing import Optional, Dict, List, Tuple
import statistics
import re
import math

# Add src to path
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.db.manager import DatabaseManager
from src.config import ConfigLoader

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)


def odds_to_implied_prob(odds: float) -> Optional[float]:
    """
    Convert odds to implied probability (no normalization).

    Args:
        odds: Decimal odds (e.g., 2.0)

    Returns:
        Implied probability or None if invalid
    """
    if not odds or odds <= 1.0:
        return None
    return 1.0 / odds


def select_reference_bookmaker(calculation_bookmaker: str) -> str:
    """
    Select which bookmaker's actual odds to use as reference for this calculation.

    Args:
        calculation_bookmaker: The bookmaker this calculation is pricing for

    Returns:
        Reference bookmaker name ('sporty' or 'bet9ja')
    """
    if calculation_bookmaker in ('pawa', 'sporty'):
        return 'sporty'
    elif calculation_bookmaker == 'bet9ja':
        return 'bet9ja'
    else:
        # Default fallback
        return 'sporty'


class EngineAnalyzer:
    """Analyzes engine calculations with proper reference-based metrics."""

    def __init__(self, db: DatabaseManager, config: ConfigLoader):
        """
        Initialize analyzer.

        Args:
            db: Connected database manager
            config: Config loader with engine settings
        """
        self.db = db
        self.config = config


    def _get_bet9ja_1up_odds(self, sportradar_id: str, scraping_history_id: int = None) -> Optional[Dict]:
        """
        Fetch Bet9ja actual 1UP odds from market_snapshots table.

        Args:
            sportradar_id: Event ID
            scraping_history_id: Optional specific snapshot

        Returns:
            Dict with 'home', 'away', 'draw' or None if not found
        """
        cursor = self.db.conn.cursor()

        if scraping_history_id:
            query = """
                SELECT
                    bet9ja_outcome_1_odds,
                    bet9ja_outcome_2_odds,
                    bet9ja_outcome_3_odds
                FROM market_snapshots
                WHERE sportradar_id = ?
                  AND scraping_history_id = ?
                  AND market_name = '1X2 - 1UP'
                LIMIT 1
            """
            cursor.execute(query, (sportradar_id, scraping_history_id))
        else:
            # Get latest snapshot for this event
            query = """
                SELECT
                    bet9ja_outcome_1_odds,
                    bet9ja_outcome_2_odds,
                    bet9ja_outcome_3_odds
                FROM market_snapshots
                WHERE sportradar_id = ?
                  AND market_name = '1X2 - 1UP'
                ORDER BY snapshot_timestamp DESC
                LIMIT 1
            """
            cursor.execute(query, (sportradar_id,))

        row = cursor.fetchone()

        if row and row[0]:  # Check if bet9ja odds exist
            return {
                'home': row[0],
                'draw': row[1],
                'away': row[2]
            }

        return None

    def analyze_all_events(self, engine_filter: Optional[str] = None, bookmaker_filter: Optional[str] = None) -> List[Dict]:
        """
        Analyze engine calculations for all bookmakers or a specific bookmaker.

        Args:
            engine_filter: Optional engine name to filter on
            bookmaker_filter: Optional bookmaker to filter ('pawa', 'sporty', 'bet9ja', or None for all)

        Returns:
            List of analysis result dicts
        """
        cursor = self.db.conn.cursor()

        # Get engine calculations (all bookmakers by default, or filtered)
        query = """
            SELECT
                ec.sportradar_id,
                ec.scraping_history_id,
                ec.engine_name,
                ec.bookmaker,
                ev.start_time,
                ev.tournament_name,
                ev.home_team,
                ev.away_team,
                ec.lambda_home,
                ec.lambda_away,
                ec.lambda_total,
                ec.p_home_1up,
                ec.p_away_1up,
                ec.fair_home,
                ec.fair_away,
                ec.fair_draw,
                ec.actual_sporty_home,
                ec.actual_sporty_away,
                ec.actual_sporty_draw
            FROM engine_calculations ec
            LEFT JOIN events ev ON ec.sportradar_id = ev.sportradar_id
            WHERE 1=1
        """

        params = []
        if bookmaker_filter:
            query += " AND ec.bookmaker = ?"
            params.append(bookmaker_filter)

        if engine_filter:
            query += " AND ec.engine_name = ?"
            params.append(engine_filter)

        query += " ORDER BY ec.bookmaker, ec.sportradar_id, ec.engine_name"

        cursor.execute(query, params)
        calculations = cursor.fetchall()

        results = []

        for calc in calculations:
            (
                sportradar_id,
                scraping_history_id,
                engine_name,
                bookmaker,
                start_time,
                tournament_name,
                home_team,
                away_team,
                lambda_home,
                lambda_away,
                lambda_total,
                p_home_1up,
                p_away_1up,
                fair_home,
                fair_away,
                fair_draw,
                actual_sporty_home,
                actual_sporty_away,
                actual_sporty_draw
            ) = calc

            # STEP 1: Select reference bookmaker for this calculation
            ref_bookmaker = select_reference_bookmaker(bookmaker)

            # STEP 2: Get reference actual odds
            if ref_bookmaker == 'sporty':
                ref_home_odds = actual_sporty_home
                ref_away_odds = actual_sporty_away
                ref_draw_odds = actual_sporty_draw
            elif ref_bookmaker == 'bet9ja':
                bet9ja_1up = self._get_bet9ja_1up_odds(sportradar_id, scraping_history_id)
                ref_home_odds = bet9ja_1up['home'] if bet9ja_1up else None
                ref_away_odds = bet9ja_1up['away'] if bet9ja_1up else None
                ref_draw_odds = bet9ja_1up['draw'] if bet9ja_1up else None
            else:
                ref_home_odds = None
                ref_away_odds = None
                ref_draw_odds = None

            # STEP 3: Compute implied probabilities from REFERENCE odds only
            ref_imp_home = odds_to_implied_prob(ref_home_odds)
            ref_imp_away = odds_to_implied_prob(ref_away_odds)

            # STEP 4: Compute probability errors vs REFERENCE (primary KPI)
            err_prob_home_ref = (p_home_1up - ref_imp_home) if (p_home_1up and ref_imp_home) else None
            err_prob_away_ref = (p_away_1up - ref_imp_away) if (p_away_1up and ref_imp_away) else None
            abs_err_prob_home_ref = abs(err_prob_home_ref) if err_prob_home_ref is not None else None
            abs_err_prob_away_ref = abs(err_prob_away_ref) if err_prob_away_ref is not None else None

            # STEP 5: Compute log-odds errors vs REFERENCE (stable metric)
            logodds_err_home_ref = None
            logodds_err_away_ref = None
            if fair_home and ref_home_odds and fair_home > 1.0 and ref_home_odds > 1.0:
                logodds_err_home_ref = abs(math.log(fair_home) - math.log(ref_home_odds))
            if fair_away and ref_away_odds and fair_away > 1.0 and ref_away_odds > 1.0:
                logodds_err_away_ref = abs(math.log(fair_away) - math.log(ref_away_odds))

            # STEP 6: Build result dict with reference-based metrics
            result = {
                'sportradar_id': sportradar_id,
                'scraping_history_id': scraping_history_id,
                'engine_name': engine_name,
                'bookmaker': bookmaker,
                'start_time': start_time,
                'tournament_name': tournament_name,
                'home_team': home_team,
                'away_team': away_team,
                'lambda_home': round(lambda_home, 4) if lambda_home else None,
                'lambda_away': round(lambda_away, 4) if lambda_away else None,
                'lambda_total': round(lambda_total, 4) if lambda_total else None,
                'p_home_1up': round(p_home_1up, 4) if p_home_1up else None,
                'p_away_1up': round(p_away_1up, 4) if p_away_1up else None,
                'fair_home': round(fair_home, 3) if fair_home else None,
                'fair_away': round(fair_away, 3) if fair_away else None,
                'fair_draw': round(fair_draw, 3) if fair_draw else None,
                # REFERENCE odds (used for all error calculations)
                'ref_bookmaker': ref_bookmaker,
                'ref_home_odds': round(ref_home_odds, 3) if ref_home_odds else None,
                'ref_away_odds': round(ref_away_odds, 3) if ref_away_odds else None,
                'ref_draw_odds': round(ref_draw_odds, 3) if ref_draw_odds else None,
                'ref_imp_home': round(ref_imp_home, 4) if ref_imp_home else None,
                'ref_imp_away': round(ref_imp_away, 4) if ref_imp_away else None,
                # REFERENCE-based errors (primary metrics)
                'err_prob_home_ref': round(err_prob_home_ref, 4) if err_prob_home_ref is not None else None,
                'err_prob_away_ref': round(err_prob_away_ref, 4) if err_prob_away_ref is not None else None,
                'abs_err_prob_home_ref': round(abs_err_prob_home_ref, 4) if abs_err_prob_home_ref else None,
                'abs_err_prob_away_ref': round(abs_err_prob_away_ref, 4) if abs_err_prob_away_ref else None,
                'logodds_err_home_ref': round(logodds_err_home_ref, 4) if logodds_err_home_ref else None,
                'logodds_err_away_ref': round(logodds_err_away_ref, 4) if logodds_err_away_ref else None,
            }

            # STEP 7: Optional - include other bookmaker odds for reference (not used in errors)
            # Only include if filter allows
            if not bookmaker_filter or bookmaker_filter in ('pawa', 'sporty'):
                result['other_sporty_home'] = round(actual_sporty_home, 3) if actual_sporty_home else None
                result['other_sporty_away'] = round(actual_sporty_away, 3) if actual_sporty_away else None
                result['other_sporty_draw'] = round(actual_sporty_draw, 3) if actual_sporty_draw else None

            if not bookmaker_filter or bookmaker_filter == 'bet9ja':
                bet9ja_1up = self._get_bet9ja_1up_odds(sportradar_id, scraping_history_id)
                if bet9ja_1up:
                    result['other_bet9ja_home'] = round(bet9ja_1up['home'], 3) if bet9ja_1up['home'] else None
                    result['other_bet9ja_away'] = round(bet9ja_1up['away'], 3) if bet9ja_1up['away'] else None
                    result['other_bet9ja_draw'] = round(bet9ja_1up['draw'], 3) if bet9ja_1up['draw'] else None

            # STEP 8: Pivot market snapshots into per-row columns (optional - for detailed analysis)
            try:
                if scraping_history_id:
                    snaps = self.db.get_snapshots_for_event(sportradar_id, scraping_history_id)
                else:
                    snaps = self.db.get_snapshots_for_event(sportradar_id)
            except Exception:
                snaps = []

            if snaps:
                def _sanitize(x: str) -> str:
                    x = (x or '')
                    x = x.lower()
                    x = re.sub(r"\s+", "_", x)
                    x = re.sub(r"[^0-9a-zA-Z_\.\-]", "_", x)
                    return x.strip('_')

                # Only include markets used by the engine
                allowed = {"1x2", "over/under", "home o/u", "away o/u"}
                for s in snaps:
                    mname = s.get('market_name') or ''
                    spec = s.get('specifier') or ''
                    # normalize market name for comparison
                    mnorm = re.sub(r"\s+", " ", mname).strip().lower()
                    if mnorm not in allowed:
                        continue

                    base = _sanitize(mname)
                    if spec not in (None, ''):
                        base = f"{base}_{_sanitize(str(spec))}"

                    col1 = f"{base}_1_odd"
                    col2 = f"{base}_2_odd"
                    col3 = f"{base}_3_odd"

                    # Use bookmaker-specific odds based on calculation target
                    if bookmaker == 'pawa':
                        o1 = s.get('pawa_outcome_1_odds')
                        o2 = s.get('pawa_outcome_2_odds')
                        o3 = s.get('pawa_outcome_3_odds')
                    elif bookmaker == 'sporty':
                        o1 = s.get('sporty_outcome_1_odds')
                        o2 = s.get('sporty_outcome_2_odds')
                        o3 = s.get('sporty_outcome_3_odds')
                    elif bookmaker == 'bet9ja':
                        o1 = s.get('bet9ja_outcome_1_odds')
                        o2 = s.get('bet9ja_outcome_2_odds')
                        o3 = s.get('bet9ja_outcome_3_odds')
                    else:
                        o1 = o2 = o3 = None

                    result[col1] = round(o1, 3) if o1 else None
                    result[col2] = round(o2, 3) if o2 else None
                    if o3 is not None:
                        result[col3] = round(o3, 3) if o3 else None

            results.append(result)

        return results

    def export_to_csv(self, results: List[Dict], output_path: Path) -> Path:
        """Export analysis results to CSV file."""
        if not results:
            logger.warning("No results to export")
            return None

        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Build ordered fieldnames: core fields, reference fields, error fields, margin fields, other fields
        core_fields = [
            'sportradar_id', 'scraping_history_id', 'engine_name', 'bookmaker',
            'start_time', 'tournament_name', 'home_team', 'away_team',
            'lambda_home', 'lambda_away', 'lambda_total',
            'p_home_1up', 'p_away_1up', 'fair_home', 'fair_away', 'fair_draw',
        ]

        reference_fields = [
            'ref_bookmaker', 'ref_home_odds', 'ref_away_odds', 'ref_draw_odds',
            'ref_imp_home', 'ref_imp_away',
        ]

        error_fields = [
            'err_prob_home_ref', 'err_prob_away_ref',
            'abs_err_prob_home_ref', 'abs_err_prob_away_ref',
            'logodds_err_home_ref', 'logodds_err_away_ref',
        ]

        # Discover extra columns (other bookmaker odds, market snapshots)
        all_keys = set()
        for r in results:
            all_keys.update(r.keys())

        other_book_cols = sorted([k for k in all_keys if k.startswith('other_')])
        market_cols = sorted([k for k in all_keys if k not in core_fields and k not in reference_fields
                             and k not in error_fields and k not in other_book_cols
                             and re.search(r"_(1|2|3)_odd$", k)])

        fieldnames = core_fields + reference_fields + error_fields + other_book_cols + market_cols

        with open(output_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(results)

        logger.info(f"Results exported to {output_path}")
        return output_path

    def print_summary(self, results: List[Dict], bookmaker_filter: Optional[str] = None):
        """Print analysis summary to terminal."""
        if not results:
            print("\n[WARNING] No analysis results available\n")
            return

        print("\n" + "=" * 80)
        print("  1UP ENGINE ANALYSIS SUMMARY")
        print("=" * 80)

        unique_events = len(set(r['sportradar_id'] for r in results))
        unique_engines = len(set(r['engine_name'] for r in results))

        print(f"\n[Dataset Overview]")
        print(f"  Events analyzed: {unique_events}")
        print(f"  Engines tested: {unique_engines}")
        print(f"  Total records: {len(results):,}")

        # Determine reference description
        if bookmaker_filter == 'pawa':
            ref_note = " (reference: Sporty odds - same provider)"
        elif bookmaker_filter == 'sporty':
            ref_note = " (reference: Sporty odds)"
        elif bookmaker_filter == 'bet9ja':
            ref_note = " (reference: Bet9ja odds)"
        else:
            ref_note = " (reference: per-row - Sporty for pawa/sporty, Bet9ja for bet9ja)"

        # Probability MAE by engine (primary KPI) - using REFERENCE errors only
        print(f"\n[Probability MAE by Engine]{ref_note}:")
        print(f"  {'Engine':<25} {'Home MAE':>12} {'Away MAE':>12} {'Records':>10}")
        print(f"  {'-'*65}")

        by_engine = {}
        for r in results:
            engine = r['engine_name']
            if engine not in by_engine:
                by_engine[engine] = {'home_ref': [], 'away_ref': []}

            # Reference errors only
            if r.get('abs_err_prob_home_ref') is not None:
                by_engine[engine]['home_ref'].append(r['abs_err_prob_home_ref'])
            if r.get('abs_err_prob_away_ref') is not None:
                by_engine[engine]['away_ref'].append(r['abs_err_prob_away_ref'])

        for engine in sorted(by_engine.keys()):
            data = by_engine[engine]
            home_errors = data['home_ref']
            away_errors = data['away_ref']

            mae_home = statistics.mean(home_errors) if home_errors else 0
            mae_away = statistics.mean(away_errors) if away_errors else 0
            count = len(home_errors)
            print(f"  {engine:<25} {mae_home:>12.4f} {mae_away:>12.4f} {count:>10}")

        # Log-odds MAE (stable metric, less sensitive to longshots)
        print(f"\n[Log-Odds MAE by Engine]{ref_note}:")
        print(f"  {'Engine':<25} {'Home Log-MAE':>15} {'Away Log-MAE':>15} {'Records':>10}")
        print(f"  {'-'*70}")

        by_engine_log = {}
        for r in results:
            engine = r['engine_name']
            if engine not in by_engine_log:
                by_engine_log[engine] = {'home': [], 'away': []}

            if r.get('logodds_err_home_ref') is not None:
                by_engine_log[engine]['home'].append(r['logodds_err_home_ref'])
            if r.get('logodds_err_away_ref') is not None:
                by_engine_log[engine]['away'].append(r['logodds_err_away_ref'])

        for engine in sorted(by_engine_log.keys()):
            home_log = by_engine_log[engine]['home']
            away_log = by_engine_log[engine]['away']
            mae_home_log = statistics.mean(home_log) if home_log else 0
            mae_away_log = statistics.mean(away_log) if away_log else 0
            count_log = len(home_log)
            print(f"  {engine:<25} {mae_home_log:>15.4f} {mae_away_log:>15.4f} {count_log:>10}")

        print("\n" + "=" * 80 + "\n")


def main():
    parser = argparse.ArgumentParser(
        description="Analyze 1UP Engine Calculations",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python analyze_engines.py                            # Full analysis (all bookmakers)
  python analyze_engines.py --bookmaker pawa           # Analyze Betpawa calculations only
  python analyze_engines.py --bookmaker sporty         # Analyze Sportybet calculations only
  python analyze_engines.py --bookmaker bet9ja         # Analyze Bet9ja calculations only
  python analyze_engines.py --engine FTS-Calibrated-DP # Single engine
  python analyze_engines.py --engine FTS-Calibrated-DP --bookmaker bet9ja  # Engine + bookmaker filter
  python analyze_engines.py -o reports                 # Custom output folder
    """
    )

    parser.add_argument(
        '--engine',
        type=str,
        default=None,
        help='Filter by engine name'
    )

    parser.add_argument(
        '--bookmaker',
        type=str,
        default=None,
        choices=['pawa', 'sporty', 'bet9ja'],
        help='Filter by bookmaker (pawa, sporty, or bet9ja) - default: all bookmakers'
    )

    parser.add_argument(
        '--output', '-o',
        type=str,
        default='reports',
        help='Output folder for CSV - default: reports'
    )

    parser.add_argument(
        '--no-csv',
        action='store_true',
        help='Skip CSV export, only print summary'
    )

    args = parser.parse_args()

    # Load config and database
    config = ConfigLoader()
    db = DatabaseManager(config.get_db_path())
    db.connect()

    try:
        # Create analyzer
        analyzer = EngineAnalyzer(db, config)

        # Analyze all events
        bookmaker_msg = f" (bookmaker: {args.bookmaker})" if args.bookmaker else " (all bookmakers)"
        print(f"\n[Analyzing events]{bookmaker_msg}...")
        results = analyzer.analyze_all_events(engine_filter=args.engine, bookmaker_filter=args.bookmaker)

        # Export to CSV
        if not args.no_csv and results:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_file = f"analysis_{timestamp}.csv"
            output_path = Path(args.output) / output_file
            analyzer.export_to_csv(results, output_path)

        # Print summary
        analyzer.print_summary(results, bookmaker_filter=args.bookmaker)

    finally:
        db.close()


if __name__ == '__main__':
    main()
