"""
Test Analysis Script for Engine Calibration

Analyzes engine results from test_engine_calculations table (populated by test_runner.py).
Compares our fair odds against Sportybet and Bet9ja fair odds.

Usage:
    python test_analyze.py                          # Full analysis
    python test_analyze.py --engine Poisson-Calibrated  # Specific engine
    python test_analyze.py --bookmaker pawa         # Specific bookmaker
    python test_analyze.py --output test_reports    # Custom output folder
"""

import argparse
import csv
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, List
import statistics

# Add src to path
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.db.manager import DatabaseManager
from src.config import ConfigLoader
from src.engine.base import devig_two_way

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)


class TestAnalyzer:
    """Analyzes test engine calculations."""

    def __init__(self, db: DatabaseManager):
        """Initialize analyzer."""
        self.db = db

    def _actual_to_fair(self, actual_home: float, actual_away: float) -> tuple:
        """Convert actual odds to fair odds (2-way devig)."""
        if not actual_home or not actual_away or actual_home <= 0 or actual_away <= 0:
            return None, None

        fair_prob_home = devig_two_way(actual_home, actual_away)
        fair_prob_away = 1.0 - fair_prob_home

        fair_home = 1.0 / fair_prob_home if fair_prob_home > 0 else None
        fair_away = 1.0 / fair_prob_away if fair_prob_away > 0 else None

        return fair_home, fair_away

    def analyze_all(
        self,
        engine_filter: Optional[str] = None,
        bookmaker_filter: Optional[str] = None
    ) -> List[Dict]:
        """
        Analyze all test calculations.

        Args:
            engine_filter: Filter by engine name
            bookmaker_filter: Filter by bookmaker

        Returns:
            List of analysis result dicts
        """
        cursor = self.db.conn.cursor()

        query = """
            SELECT
                tec.id,
                tec.sportradar_id,
                tec.scraping_history_id,
                tec.engine_name,
                tec.bookmaker,
                ev.start_time,
                ev.tournament_name,
                ev.home_team,
                ev.away_team,
                tec.lambda_home,
                tec.lambda_away,
                tec.lambda_total,
                tec.p_home_1up,
                tec.p_away_1up,
                tec.fair_home,
                tec.fair_away,
                tec.fair_draw,
                tec.actual_sporty_home,
                tec.actual_sporty_away,
                tec.actual_sporty_draw,
                tec.actual_bet9ja_home,
                tec.actual_bet9ja_away,
                tec.actual_bet9ja_draw,
                tec.extra_data,
                tec.calculated_at
            FROM test_engine_calculations tec
            LEFT JOIN events ev ON tec.sportradar_id = ev.sportradar_id
            WHERE 1=1
        """

        params = []
        if engine_filter:
            query += " AND tec.engine_name = ?"
            params.append(engine_filter)

        if bookmaker_filter:
            query += " AND tec.bookmaker = ?"
            params.append(bookmaker_filter)

        query += " ORDER BY tec.bookmaker, tec.engine_name, tec.calculated_at DESC"

        cursor.execute(query, params)
        calculations = cursor.fetchall()

        results = []

        for calc in calculations:
            (
                calc_id, sportradar_id, scraping_history_id, engine_name, bookmaker,
                start_time, tournament_name, home_team, away_team,
                lambda_home, lambda_away, lambda_total,
                p_home_1up, p_away_1up,
                fair_home, fair_away, fair_draw,
                actual_sporty_home, actual_sporty_away, actual_sporty_draw,
                actual_bet9ja_home, actual_bet9ja_away, actual_bet9ja_draw,
                extra_data, calculated_at
            ) = calc

            # Calculate fair odds from actuals
            sporty_fair_home, sporty_fair_away = self._actual_to_fair(actual_sporty_home, actual_sporty_away)
            bet9ja_fair_home, bet9ja_fair_away = self._actual_to_fair(actual_bet9ja_home, actual_bet9ja_away)

            # Parse extra data
            import json
            extra = {}
            if extra_data:
                try:
                    extra = json.loads(extra_data)
                except:
                    pass

            result = {
                'calc_id': calc_id,
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
                'lambda_ratio': round(extra.get('lambda_ratio', 0), 4) if extra.get('lambda_ratio') else None,
                'p_home_1up': round(p_home_1up, 4) if p_home_1up else None,
                'p_away_1up': round(p_away_1up, 4) if p_away_1up else None,
                'p_home_1up_raw': round(extra.get('p_home_1up_raw', 0), 4) if extra.get('p_home_1up_raw') else None,
                'p_away_1up_raw': round(extra.get('p_away_1up_raw', 0), 4) if extra.get('p_away_1up_raw') else None,
                'fair_home': round(fair_home, 3) if fair_home else None,
                'fair_away': round(fair_away, 3) if fair_away else None,
                'fair_draw': round(fair_draw, 3) if fair_draw else None,
                # Sportybet comparison
                'sporty_actual_home': round(actual_sporty_home, 3) if actual_sporty_home else None,
                'sporty_actual_away': round(actual_sporty_away, 3) if actual_sporty_away else None,
                'sporty_fair_home': round(sporty_fair_home, 3) if sporty_fair_home else None,
                'sporty_fair_away': round(sporty_fair_away, 3) if sporty_fair_away else None,
                'sporty_home_diff': round(fair_home - sporty_fair_home, 3) if fair_home and sporty_fair_home else None,
                'sporty_away_diff': round(fair_away - sporty_fair_away, 3) if fair_away and sporty_fair_away else None,
                # Bet9ja comparison
                'bet9ja_actual_home': round(actual_bet9ja_home, 3) if actual_bet9ja_home else None,
                'bet9ja_actual_away': round(actual_bet9ja_away, 3) if actual_bet9ja_away else None,
                'bet9ja_fair_home': round(bet9ja_fair_home, 3) if bet9ja_fair_home else None,
                'bet9ja_fair_away': round(bet9ja_fair_away, 3) if bet9ja_fair_away else None,
                'bet9ja_home_diff': round(fair_home - bet9ja_fair_home, 3) if fair_home and bet9ja_fair_home else None,
                'bet9ja_away_diff': round(fair_away - bet9ja_fair_away, 3) if fair_away and bet9ja_fair_away else None,
                'calculated_at': calculated_at,
            }

            results.append(result)

        return results

    def export_to_csv(self, results: List[Dict], output_path: Path) -> Path:
        """Export analysis results to CSV."""
        if not results:
            logger.warning("No results to export")
            return None

        output_path.parent.mkdir(parents=True, exist_ok=True)

        fieldnames = [
            'calc_id', 'sportradar_id', 'scraping_history_id', 'engine_name', 'bookmaker',
            'start_time', 'tournament_name', 'home_team', 'away_team',
            'lambda_home', 'lambda_away', 'lambda_total', 'lambda_ratio',
            'p_home_1up', 'p_away_1up', 'p_home_1up_raw', 'p_away_1up_raw',
            'fair_home', 'fair_away', 'fair_draw',
            'sporty_actual_home', 'sporty_actual_away',
            'sporty_fair_home', 'sporty_fair_away',
            'sporty_home_diff', 'sporty_away_diff',
            'bet9ja_actual_home', 'bet9ja_actual_away',
            'bet9ja_fair_home', 'bet9ja_fair_away',
            'bet9ja_home_diff', 'bet9ja_away_diff',
            'calculated_at'
        ]

        with open(output_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(results)

        logger.info(f"Results exported to {output_path}")
        return output_path

    def print_summary(self, results: List[Dict]):
        """Print analysis summary."""
        if not results:
            print("\n⚠️  No analysis results available\n")
            return

        print("\n" + "=" * 100)
        print("  TEST ENGINE ANALYSIS SUMMARY")
        print("=" * 100)

        unique_events = len(set(r['sportradar_id'] for r in results))
        unique_engines = len(set(r['engine_name'] for r in results))
        unique_bookmakers = len(set(r['bookmaker'] for r in results))

        print(f"\n📊 Dataset Overview:")
        print(f"  Events analyzed: {unique_events}")
        print(f"  Engines tested: {unique_engines}")
        print(f"  Bookmakers: {unique_bookmakers}")
        print(f"  Total calculations: {len(results):,}")

        # Overall fair odds difference
        print(f"\n📈 Overall Fair Odds Difference (our_fair - market_fair):")
        print(f"  {'Source':<15} {'Avg Home Diff':>15} {'Avg Away Diff':>15} {'Count':>10}")
        print(f"  {'-'*60}")

        # Sportybet differences
        sporty_home = [r['sporty_home_diff'] for r in results if r.get('sporty_home_diff') is not None]
        sporty_away = [r['sporty_away_diff'] for r in results if r.get('sporty_away_diff') is not None]
        if sporty_home or sporty_away:
            avg_sporty_home = statistics.mean(sporty_home) if sporty_home else 0
            avg_sporty_away = statistics.mean(sporty_away) if sporty_away else 0
            print(f"  {'Sportybet':<15} {avg_sporty_home:>15.4f} {avg_sporty_away:>15.4f} {len(sporty_home):>10}")

        # Bet9ja differences
        bet9ja_home = [r['bet9ja_home_diff'] for r in results if r.get('bet9ja_home_diff') is not None]
        bet9ja_away = [r['bet9ja_away_diff'] for r in results if r.get('bet9ja_away_diff') is not None]
        if bet9ja_home or bet9ja_away:
            avg_bet9ja_home = statistics.mean(bet9ja_home) if bet9ja_home else 0
            avg_bet9ja_away = statistics.mean(bet9ja_away) if bet9ja_away else 0
            print(f"  {'Bet9ja':<15} {avg_bet9ja_home:>15.4f} {avg_bet9ja_away:>15.4f} {len(bet9ja_home):>10}")

        # By engine
        print(f"\n📊 By Engine:")
        print(f"  {'Engine':<25} {'Sporty Home':>12} {'Sporty Away':>12} {'Bet9ja Home':>12} {'Bet9ja Away':>12} {'Count':>8}")
        print(f"  {'-'*85}")

        by_engine = {}
        for r in results:
            engine = r['engine_name']
            if engine not in by_engine:
                by_engine[engine] = {
                    'sporty_home': [],
                    'sporty_away': [],
                    'bet9ja_home': [],
                    'bet9ja_away': []
                }

            if r.get('sporty_home_diff') is not None:
                by_engine[engine]['sporty_home'].append(r['sporty_home_diff'])
            if r.get('sporty_away_diff') is not None:
                by_engine[engine]['sporty_away'].append(r['sporty_away_diff'])
            if r.get('bet9ja_home_diff') is not None:
                by_engine[engine]['bet9ja_home'].append(r['bet9ja_home_diff'])
            if r.get('bet9ja_away_diff') is not None:
                by_engine[engine]['bet9ja_away'].append(r['bet9ja_away_diff'])

        for engine in sorted(by_engine.keys()):
            data = by_engine[engine]
            avg_sh = statistics.mean(data['sporty_home']) if data['sporty_home'] else 0
            avg_sa = statistics.mean(data['sporty_away']) if data['sporty_away'] else 0
            avg_bh = statistics.mean(data['bet9ja_home']) if data['bet9ja_home'] else 0
            avg_ba = statistics.mean(data['bet9ja_away']) if data['bet9ja_away'] else 0
            count = max(len(data['sporty_home']), len(data['bet9ja_home']))
            print(f"  {engine:<25} {avg_sh:>12.4f} {avg_sa:>12.4f} {avg_bh:>12.4f} {avg_ba:>12.4f} {count:>8}")

        # Lambda ratio analysis
        print(f"\n🎯 By Lambda Ratio (underdog/favorite strength):")
        print(f"  {'Ratio Range':<15} {'Sporty Home':>12} {'Sporty Away':>12} {'Count':>8}")
        print(f"  {'-'*50}")

        # Group by lambda ratio
        ratio_buckets = {
            '1.0-1.2': [],
            '1.2-1.8': [],
            '1.8-2.5': [],
            '>2.5': []
        }

        for r in results:
            ratio = r.get('lambda_ratio')
            if ratio is None:
                continue

            if ratio <= 1.2:
                bucket = '1.0-1.2'
            elif ratio <= 1.8:
                bucket = '1.2-1.8'
            elif ratio <= 2.5:
                bucket = '1.8-2.5'
            else:
                bucket = '>2.5'

            ratio_buckets[bucket].append(r)

        for bucket, items in ratio_buckets.items():
            if not items:
                continue

            sh = [r['sporty_home_diff'] for r in items if r.get('sporty_home_diff') is not None]
            sa = [r['sporty_away_diff'] for r in items if r.get('sporty_away_diff') is not None]

            avg_sh = statistics.mean(sh) if sh else 0
            avg_sa = statistics.mean(sa) if sa else 0

            print(f"  {bucket:<15} {avg_sh:>12.4f} {avg_sa:>12.4f} {len(items):>8}")

        print("\n" + "=" * 100 + "\n")


def main():
    parser = argparse.ArgumentParser(
        description="Test Analysis for Engine Calibration",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python test_analyze.py                              # Full analysis
  python test_analyze.py --engine Poisson-Calibrated  # Specific engine
  python test_analyze.py --bookmaker pawa             # Specific bookmaker
  python test_analyze.py --output test_reports        # Custom output folder
  python test_analyze.py --no-csv                     # Skip CSV export
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
        help='Filter by bookmaker'
    )

    parser.add_argument(
        '--output', '-o',
        type=str,
        default='test_reports',
        help='Output folder for CSV'
    )

    parser.add_argument(
        '--no-csv',
        action='store_true',
        help='Skip CSV export'
    )

    args = parser.parse_args()

    # Load config and connect to database
    config = ConfigLoader()
    db = DatabaseManager(config.get_db_path())
    db.connect()

    try:
        analyzer = TestAnalyzer(db)

        # Analyze
        bookmaker_msg = f" (bookmaker: {args.bookmaker})" if args.bookmaker else ""
        engine_msg = f" (engine: {args.engine})" if args.engine else ""
        print(f"\n🔍 Analyzing test calculations{engine_msg}{bookmaker_msg}...")

        results = analyzer.analyze_all(
            engine_filter=args.engine,
            bookmaker_filter=args.bookmaker
        )

        # Export to CSV
        if not args.no_csv and results:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_file = f"test_analysis_{timestamp}.csv"
            output_path = Path(args.output) / output_file
            analyzer.export_to_csv(results, output_path)

        # Print summary
        analyzer.print_summary(results)

    finally:
        db.close()


if __name__ == '__main__':
    main()
