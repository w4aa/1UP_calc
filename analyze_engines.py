"""
1UP Engine Analysis Script

Analyzes engine calculation results stored in the database.
For each event/engine with bookmaker='pawa':
- Get fair odds (fair_home, fair_away, fair_draw)
- Apply margins from engine.yaml config to calculate 1UP odds
- Compare with actual Sportybet 1UP odds

Usage:
    python analyze_engines.py                    # Full analysis with all margins
    python analyze_engines.py --margin 0.06      # Specific margin (6%)
    python analyze_engines.py --engine poisson   # Specific engine
    python analyze_engines.py --output reports   # Custom output folder
"""

import argparse
import csv
import logging
import sys
from datetime import datetime
import json
from pathlib import Path
from typing import Optional, Dict, List
import statistics
import re

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


class EngineAnalyzer:
    """Analyzes engine calculations with margin application."""
    
    def __init__(self, db: DatabaseManager, config: ConfigLoader, margins: Optional[List[float]] = None):
        """
        Initialize analyzer.
        
        Args:
            db: Connected database manager
            config: Config loader with engine settings
            margins: List of margins to analyze (default: from engine.yaml config)
        """
        self.db = db
        self.config = config
        
        # Use margins from config if not explicitly provided
        if margins is not None:
            self.margins = margins
        else:
            self.margins = config.get_engine_test_margins()
    
    def _apply_margin_to_1up(self, p_home_1up: float, p_away_1up: float, margin: float) -> tuple:
        """
        Apply margin to 1UP probabilities (2-way market: home/away only).
        
        Args:
            p_home_1up: Fair probability of home 1UP
            p_away_1up: Fair probability of away 1UP
            margin: Target margin (e.g., 0.05 for 5%)
            
        Returns:
            Tuple of (home_odds, away_odds) with margin applied
        """
        if not p_home_1up or not p_away_1up or p_home_1up <= 0 or p_away_1up <= 0:
            return None, None
        
        # Total fair probability (should be ~1.0 for complementary outcomes)
        total_fair = p_home_1up + p_away_1up
        
        # Target total with margin
        target_total = 1.0 + margin
        
        # Scale probabilities to include margin
        scale_factor = target_total / total_fair
        p_home_margin = p_home_1up * scale_factor
        p_away_margin = p_away_1up * scale_factor
        
        # Convert to odds
        home_odds = 1.0 / p_home_margin if p_home_margin > 0 else None
        away_odds = 1.0 / p_away_margin if p_away_margin > 0 else None
        
        return home_odds, away_odds
    
    def _actual_to_fair(self, actual_home: float, actual_away: float) -> tuple:
        """
        Convert actual odds (with margin) to fair odds (2-way market only).

        Args:
            actual_home: Actual home odds with margin
            actual_away: Actual away odds with margin

        Returns:
            Tuple of (fair_home, fair_away) odds
        """
        if not actual_home or not actual_away or actual_home <= 0 or actual_away <= 0:
            return None, None

        # Use centralized de-vigging function from base.py
        fair_prob_home = devig_two_way(actual_home, actual_away)
        fair_prob_away = 1.0 - fair_prob_home

        # Convert back to odds
        fair_home = 1.0 / fair_prob_home if fair_prob_home > 0 else None
        fair_away = 1.0 / fair_prob_away if fair_prob_away > 0 else None

        return fair_home, fair_away

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
        
        # Prepare margin columns for later use
        self._margin_columns = []
        for margin in self.margins:
            pct = int(round(margin * 100))
            self._margin_columns.extend([
                f'pawa_{pct}_home', f'pawa_{pct}_away',
                f'pawa_{pct}_home_diff', f'pawa_{pct}_away_diff',
            ])

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

            actual_fair_home, actual_fair_away = self._actual_to_fair(actual_sporty_home, actual_sporty_away)

            # Also fetch Bet9ja actual 1UP for dual comparison
            bet9ja_1up = self._get_bet9ja_1up_odds(sportradar_id, scraping_history_id)
            bet9ja_actual_home = bet9ja_1up['home'] if bet9ja_1up else None
            bet9ja_actual_away = bet9ja_1up['away'] if bet9ja_1up else None
            bet9ja_actual_draw = bet9ja_1up['draw'] if bet9ja_1up else None
            bet9ja_fair_home, bet9ja_fair_away = self._actual_to_fair(bet9ja_actual_home, bet9ja_actual_away)

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
                'pawa_draw': round(fair_draw, 3) if fair_draw else None,
                # Sportybet actual 1UP comparison
                'sporty_h_1up': round(actual_sporty_home, 3) if actual_sporty_home else None,
                'sporty_a_1up': round(actual_sporty_away, 3) if actual_sporty_away else None,
                'draw': round(actual_sporty_draw, 3) if actual_sporty_draw else None,
                'sporty_fair_h': round(actual_fair_home, 3) if actual_fair_home else None,
                'sporty_fair_a': round(actual_fair_away, 3) if actual_fair_away else None,
                'home_fair_diff': round(fair_home - actual_fair_home, 3) if fair_home and actual_fair_home else None,
                'away_fair_diff': round(fair_away - actual_fair_away, 3) if fair_away and actual_fair_away else None,
                # Bet9ja actual 1UP comparison
                'bet9ja_h_1up': round(bet9ja_actual_home, 3) if bet9ja_actual_home else None,
                'bet9ja_a_1up': round(bet9ja_actual_away, 3) if bet9ja_actual_away else None,
                'bet9ja_draw': round(bet9ja_actual_draw, 3) if bet9ja_actual_draw else None,
                'bet9ja_fair_h': round(bet9ja_fair_home, 3) if bet9ja_fair_home else None,
                'bet9ja_fair_a': round(bet9ja_fair_away, 3) if bet9ja_fair_away else None,
                'bet9ja_home_diff': round(fair_home - bet9ja_fair_home, 3) if fair_home and bet9ja_fair_home else None,
                'bet9ja_away_diff': round(fair_away - bet9ja_fair_away, 3) if fair_away and bet9ja_fair_away else None,
            }

            # For each margin, apply to fair probabilities and add columns
            for margin in self.margins:
                pct = int(round(margin * 100))
                pawa_home, pawa_away = self._apply_margin_to_1up(p_home_1up, p_away_1up, margin)
                result[f'pawa_{pct}_home'] = round(pawa_home, 3) if pawa_home else None
                result[f'pawa_{pct}_away'] = round(pawa_away, 3) if pawa_away else None
                result[f'pawa_{pct}_home_diff'] = round((pawa_home - actual_sporty_home), 3) if pawa_home and actual_sporty_home else None
                result[f'pawa_{pct}_away_diff'] = round((pawa_away - actual_sporty_away), 3) if pawa_away and actual_sporty_away else None

            # Pivot market snapshots into per-row columns (market_specifier_1_odd, _2_odd, _3_odd)
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
                    # Add pawa odds (may be None). Many specifier markets (OU lines) only have 2 outcomes,
                    # so only include the 3rd column when a 3rd outcome exists.
                    o1 = s.get('pawa_outcome_1_odds')
                    o2 = s.get('pawa_outcome_2_odds')
                    o3 = s.get('pawa_outcome_3_odds')
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
        
        # Build ordered fieldnames: core fields, dynamically discovered market columns, then margin columns
        core_fields = [
            'sportradar_id', 'scraping_history_id', 'engine_name', 'bookmaker',
            'start_time', 'tournament_name', 'home_team', 'away_team',
            'lambda_home', 'lambda_away', 'lambda_total',
            'p_home_1up', 'p_away_1up', 'fair_home', 'fair_away', 'pawa_draw',
            # Sportybet actual 1UP comparison
            'sporty_h_1up', 'sporty_a_1up', 'draw', 'sporty_fair_h', 'sporty_fair_a',
            'home_fair_diff', 'away_fair_diff',
            # Bet9ja actual 1UP comparison
            'bet9ja_h_1up', 'bet9ja_a_1up', 'bet9ja_draw', 'bet9ja_fair_h', 'bet9ja_fair_a',
            'bet9ja_home_diff', 'bet9ja_away_diff'
        ]

        margin_cols = getattr(self, '_margin_columns', [])

        # Discover extra market columns created from snapshots
        all_keys = set()
        for r in results:
            all_keys.update(r.keys())

        # Only keep pivoted pawa market columns (they end with _1_odd/_2_odd/_3_odd)
        extra_cols = sorted(
            [
                k for k in all_keys
                if k not in core_fields and k not in margin_cols and re.search(r"_(1|2|3)_odd$", k)
            ]
        )

        fieldnames = core_fields + extra_cols + margin_cols
        
        with open(output_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(results)
        
        logger.info(f"Results exported to {output_path}")
        return output_path
    
    def print_summary(self, results: List[Dict]):
        """Print analysis summary to terminal."""
        if not results:
            print("\n⚠️  No analysis results available\n")
            return
        
        print("\n" + "=" * 80)
        print("  1UP ENGINE ANALYSIS SUMMARY")
        print("=" * 80)
        
        unique_events = len(set(r['sportradar_id'] for r in results))
        unique_engines = len(set(r['engine_name'] for r in results))
        
        print(f"\n📊 Dataset Overview:")
        print(f"  Events analyzed: {unique_events}")
        print(f"  Engines tested: {unique_engines}")
        print(f"  Total records: {len(results):,}")
        
        # Fair diff by engine
        print(f"\n📈 Fair Odds Difference by Engine (fair - actual_fair):")
        print(f"  {'Engine':<20} {'Avg Home Diff':>14} {'Avg Away Diff':>14} {'Records':>10}")
        print(f"  {'-'*60}")
        
        by_engine = {}
        for r in results:
            engine = r['engine_name']
            if engine not in by_engine:
                by_engine[engine] = {'home': [], 'away': []}
            
            if r.get('home_fair_diff') is not None:
                by_engine[engine]['home'].append(r['home_fair_diff'])
            if r.get('away_fair_diff') is not None:
                by_engine[engine]['away'].append(r['away_fair_diff'])
        
        for engine in sorted(by_engine.keys()):
            home_diffs = by_engine[engine]['home']
            away_diffs = by_engine[engine]['away']
            avg_home = statistics.mean(home_diffs) if home_diffs else 0
            avg_away = statistics.mean(away_diffs) if away_diffs else 0
            count = len(home_diffs)
            print(f"  {engine:<20} {avg_home:>14.4f} {avg_away:>14.4f} {count:>10}")
        
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
  python analyze_engines.py --margin 0.06              # Single margin (6%)
  python analyze_engines.py --engine poisson           # Single engine
  python analyze_engines.py --engine poisson --bookmaker bet9ja  # Engine + bookmaker filter
  python analyze_engines.py -o reports                 # Custom output folder
    """
    )
    
    parser.add_argument(
        '--margin',
        type=float,
        default=None,
        help='Analyze specific margin, e.g. 0.06 for 6 percent'
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
        margins = [args.margin] if args.margin else None
        analyzer = EngineAnalyzer(db, config, margins=margins)

        # Analyze all events
        bookmaker_msg = f" (bookmaker: {args.bookmaker})" if args.bookmaker else " (all bookmakers)"
        print(f"\n🔍 Analyzing events{bookmaker_msg}...")
        results = analyzer.analyze_all_events(engine_filter=args.engine, bookmaker_filter=args.bookmaker)
        
        # Export to CSV
        if not args.no_csv and results:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_file = f"analysis_{timestamp}.csv"
            output_path = Path(args.output) / output_file
            analyzer.export_to_csv(results, output_path)
        
        # Print summary
        analyzer.print_summary(results)
        
    finally:
        db.close()


if __name__ == '__main__':
    main()
