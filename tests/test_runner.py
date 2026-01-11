"""
Test Runner for Engine Calibration

This script recalculates engine results for all existing market snapshots,
storing them in a test_engine_calculations table. This allows rapid iteration
on calibration improvements without needing new market data.

Usage:
    python test_runner.py                           # Run all engines on all snapshots
    python test_runner.py --engine Poisson-Calibrated  # Test specific engine
    python test_runner.py --clear                   # Clear test table first
    python test_runner.py --bookmaker pawa          # Test specific bookmaker
    python test_runner.py --limit 100               # Limit to first N snapshots
"""

import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, List

# Add src to path
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.db.manager import DatabaseManager
from src.config import ConfigLoader
from src.engine.poisson_calibrated import CalibratedPoissonEngine

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)


class TestRunner:
    """Runs engine calculations on existing snapshots for testing."""

    def __init__(self, db: DatabaseManager, config: ConfigLoader):
        """
        Initialize test runner.

        Args:
            db: Connected database manager
            config: Config loader
        """
        self.db = db
        self.config = config
        self.engines = {
            'Poisson-Calibrated': CalibratedPoissonEngine(n_sims=30000, match_minutes=95)
        }

    def _create_test_table(self):
        """Create test_engine_calculations table (mirrors engine_calculations)."""
        cursor = self.db.conn.cursor()

        # Drop and recreate for clean slate
        cursor.execute("DROP TABLE IF EXISTS test_engine_calculations")

        cursor.execute("""
            CREATE TABLE test_engine_calculations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sportradar_id TEXT NOT NULL,
                scraping_history_id INTEGER,

                -- Engine info
                engine_name TEXT NOT NULL,
                bookmaker TEXT NOT NULL,

                -- Input lambdas
                lambda_home REAL,
                lambda_away REAL,
                lambda_total REAL,

                -- 1UP probabilities
                p_home_1up REAL,
                p_away_1up REAL,

                -- Fair odds (no margin)
                fair_home REAL,
                fair_away REAL,
                fair_draw REAL,

                -- Actual odds for comparison
                actual_sporty_home REAL,
                actual_sporty_draw REAL,
                actual_sporty_away REAL,
                actual_bet9ja_home REAL,
                actual_bet9ja_draw REAL,
                actual_bet9ja_away REAL,

                -- Extra debug info (stored as JSON string)
                extra_data TEXT,

                -- Metadata
                calculated_at TEXT DEFAULT CURRENT_TIMESTAMP,

                FOREIGN KEY (sportradar_id) REFERENCES events(sportradar_id),
                FOREIGN KEY (scraping_history_id) REFERENCES scraping_history(id)
            )
        """)

        self.db.conn.commit()
        logger.info("Created test_engine_calculations table")

    def _get_market_snapshots(
        self,
        bookmaker_filter: Optional[str] = None,
        limit: Optional[int] = None
    ) -> List[Dict]:
        """
        Get all unique market snapshots from the database.

        Args:
            bookmaker_filter: Filter by bookmaker ('pawa', 'sporty', 'bet9ja')
            limit: Limit number of snapshots returned

        Returns:
            List of dicts with snapshot info
        """
        cursor = self.db.conn.cursor()

        # Get unique scraping_history_id values (each represents a complete snapshot)
        query = """
            SELECT DISTINCT
                sh.id as scraping_history_id,
                sh.sportradar_id,
                sh.scraped_at,
                e.home_team,
                e.away_team,
                e.tournament_name
            FROM scraping_history sh
            JOIN events e ON sh.sportradar_id = e.sportradar_id
            ORDER BY sh.scraped_at DESC
        """

        if limit:
            query += f" LIMIT {limit}"

        cursor.execute(query)
        rows = cursor.fetchall()

        snapshots = []
        for row in rows:
            snapshots.append({
                'scraping_history_id': row[0],
                'sportradar_id': row[1],
                'scraped_at': row[2],
                'home_team': row[3],
                'away_team': row[4],
                'tournament_name': row[5]
            })

        return snapshots

    def _get_markets_for_snapshot(
        self,
        sportradar_id: str,
        scraping_history_id: int,
        bookmaker: str
    ) -> Optional[Dict]:
        """
        Get market data for a specific snapshot in engine format.

        Args:
            sportradar_id: Event ID
            scraping_history_id: Snapshot ID
            bookmaker: 'pawa', 'sporty', or 'bet9ja'

        Returns:
            Dict with market data in engine format, or None if incomplete
        """
        snapshots = self.db.get_snapshots_for_event(sportradar_id, scraping_history_id)

        if not snapshots:
            return None

        # Build markets dict in engine format
        markets = {}

        # Determine which bookmaker columns to use
        if bookmaker == 'pawa':
            odds_prefix = 'pawa'
        elif bookmaker == 'sporty':
            odds_prefix = 'sporty'
        elif bookmaker == 'bet9ja':
            odds_prefix = 'bet9ja'
        else:
            return None

        # Track actual 1UP odds for comparison
        actual_1up = None

        for snap in snapshots:
            market_name_raw = snap.get('market_name', '')
            market_name = market_name_raw.lower()
            specifier = snap.get('specifier', '') or ''

            # Get odds based on bookmaker
            o1 = snap.get(f'{odds_prefix}_outcome_1_odds')
            o2 = snap.get(f'{odds_prefix}_outcome_2_odds')
            o3 = snap.get(f'{odds_prefix}_outcome_3_odds')

            # Skip if missing odds
            if o1 is None or o2 is None:
                continue

            # Parse market
            if market_name == '1x2' and (not specifier or specifier == ''):
                markets['1x2'] = (o1, o2, o3)

            elif market_name == '1x2 - 1up':
                # Store for comparison
                actual_1up = {'home': o1, 'draw': o2, 'away': o3}

            elif market_name == 'over/under':
                # Parse specifier like "total=2.5"
                if 'total=' in specifier:
                    try:
                        line = float(specifier.split('=')[1])
                        if 'total_ou' not in markets:
                            markets['total_ou'] = []
                        markets['total_ou'].append((line, o1, o2))
                    except (ValueError, IndexError):
                        continue

            elif market_name == 'home o/u':
                # Parse specifier like "total=1.5"
                if 'total=' in specifier:
                    try:
                        line = float(specifier.split('=')[1])
                        if 'home_ou' not in markets:
                            markets['home_ou'] = []
                        markets['home_ou'].append((line, o1, o2))
                    except (ValueError, IndexError):
                        continue

            elif market_name == 'away o/u':
                # Parse specifier like "total=1.5"
                if 'total=' in specifier:
                    try:
                        line = float(specifier.split('=')[1])
                        if 'away_ou' not in markets:
                            markets['away_ou'] = []
                        markets['away_ou'].append((line, o1, o2))
                    except (ValueError, IndexError):
                        continue

        # Validate required markets
        if not all([
            markets.get('1x2'),
            markets.get('total_ou'),
            markets.get('home_ou'),
            markets.get('away_ou')
        ]):
            return None

        return {
            'markets': markets,
            'actual_1up': actual_1up
        }

    def _store_calculation(
        self,
        sportradar_id: str,
        scraping_history_id: int,
        engine_name: str,
        bookmaker: str,
        result: Dict,
        actual_sporty: Optional[Dict] = None,
        actual_bet9ja: Optional[Dict] = None
    ):
        """Store calculation result in test_engine_calculations table."""
        cursor = self.db.conn.cursor()

        # Extract extra data for debugging
        import json
        extra_keys = ['p_home_win', 'p_draw', 'p_away_win', 'p_home_1up_raw',
                      'p_away_1up_raw', 'lambda_ratio', 'correction_applied']
        extra_data = {k: result.get(k) for k in extra_keys if k in result}

        cursor.execute("""
            INSERT INTO test_engine_calculations (
                sportradar_id, scraping_history_id, engine_name, bookmaker,
                lambda_home, lambda_away, lambda_total,
                p_home_1up, p_away_1up,
                fair_home, fair_away, fair_draw,
                actual_sporty_home, actual_sporty_draw, actual_sporty_away,
                actual_bet9ja_home, actual_bet9ja_draw, actual_bet9ja_away,
                extra_data
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            sportradar_id,
            scraping_history_id,
            engine_name,
            bookmaker,
            result.get('lambda_home'),
            result.get('lambda_away'),
            result.get('lambda_total'),
            result.get('p_home_1up'),
            result.get('p_away_1up'),
            result.get('1up_home_fair'),
            result.get('1up_away_fair'),
            result.get('1up_draw'),
            actual_sporty['home'] if actual_sporty else None,
            actual_sporty['draw'] if actual_sporty else None,
            actual_sporty['away'] if actual_sporty else None,
            actual_bet9ja['home'] if actual_bet9ja else None,
            actual_bet9ja['draw'] if actual_bet9ja else None,
            actual_bet9ja['away'] if actual_bet9ja else None,
            json.dumps(extra_data)
        ))

    def run(
        self,
        engine_filter: Optional[str] = None,
        bookmaker_filter: Optional[str] = None,
        limit: Optional[int] = None,
        clear_first: bool = False
    ):
        """
        Run test calculations on all snapshots.

        Args:
            engine_filter: Only test this engine
            bookmaker_filter: Only test this bookmaker
            limit: Limit number of snapshots to process
            clear_first: Clear test table before running
        """
        if clear_first:
            self._create_test_table()

        # Get snapshots
        snapshots = self._get_market_snapshots(bookmaker_filter, limit)
        logger.info(f"Found {len(snapshots)} snapshots to process")

        if not snapshots:
            logger.warning("No snapshots found to process")
            return

        # Determine which engines to test
        engines_to_test = {}
        if engine_filter:
            if engine_filter in self.engines:
                engines_to_test[engine_filter] = self.engines[engine_filter]
            else:
                logger.error(f"Unknown engine: {engine_filter}")
                return
        else:
            engines_to_test = self.engines

        # Determine which bookmakers to test
        bookmakers = ['pawa', 'sporty', 'bet9ja'] if not bookmaker_filter else [bookmaker_filter]

        # Process snapshots
        total_calculations = 0
        failed_calculations = 0

        for i, snapshot in enumerate(snapshots, 1):
            sportradar_id = snapshot['sportradar_id']
            scraping_history_id = snapshot['scraping_history_id']

            logger.info(f"\n[{i}/{len(snapshots)}] Processing {snapshot['home_team']} vs {snapshot['away_team']}")

            for bookmaker in bookmakers:
                # Get markets for this bookmaker
                data = self._get_markets_for_snapshot(sportradar_id, scraping_history_id, bookmaker)

                if not data:
                    logger.debug(f"  {bookmaker}: Incomplete market data, skipping")
                    continue

                markets = data['markets']
                actual_1up = data.get('actual_1up')

                # Run each engine
                for engine_name, engine in engines_to_test.items():
                    try:
                        result = engine.calculate(markets, bookmaker)

                        if result:
                            # Store calculation
                            actual_sporty = actual_1up if bookmaker == 'sporty' else None
                            actual_bet9ja = actual_1up if bookmaker == 'bet9ja' else None

                            self._store_calculation(
                                sportradar_id,
                                scraping_history_id,
                                engine_name,
                                bookmaker,
                                result,
                                actual_sporty,
                                actual_bet9ja
                            )

                            total_calculations += 1
                            logger.info(f"  ✓ {bookmaker}/{engine_name}: λ_home={result['lambda_home']:.3f}, "
                                      f"λ_away={result['lambda_away']:.3f}, "
                                      f"p_home={result['p_home_1up']:.4f}, p_away={result['p_away_1up']:.4f}")
                        else:
                            failed_calculations += 1
                            logger.warning(f"  ✗ {bookmaker}/{engine_name}: Calculation returned None")

                    except Exception as e:
                        failed_calculations += 1
                        logger.error(f"  ✗ {bookmaker}/{engine_name}: Error - {e}", exc_info=True)

        # Commit all inserts
        self.db.conn.commit()

        logger.info(f"\n{'='*80}")
        logger.info(f"Test run complete!")
        logger.info(f"  Total calculations: {total_calculations}")
        logger.info(f"  Failed calculations: {failed_calculations}")
        total_attempts = total_calculations + failed_calculations
        if total_attempts > 0:
            logger.info(f"  Success rate: {100*total_calculations/total_attempts:.1f}%")
        logger.info(f"{'='*80}\n")


def main():
    parser = argparse.ArgumentParser(
        description="Test Runner for Engine Calibration",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python test_runner.py                              # Run all engines, all bookmakers
  python test_runner.py --clear                      # Clear test table first
  python test_runner.py --engine Poisson-Calibrated  # Test specific engine
  python test_runner.py --bookmaker pawa             # Test Betpawa only
  python test_runner.py --limit 50                   # Test first 50 snapshots
  python test_runner.py --clear --limit 100          # Fresh run on 100 snapshots
        """
    )

    parser.add_argument(
        '--engine',
        type=str,
        default=None,
        help='Test specific engine only'
    )

    parser.add_argument(
        '--bookmaker',
        type=str,
        default=None,
        choices=['pawa', 'sporty', 'bet9ja'],
        help='Test specific bookmaker only'
    )

    parser.add_argument(
        '--limit',
        type=int,
        default=None,
        help='Limit number of snapshots to process'
    )

    parser.add_argument(
        '--clear',
        action='store_true',
        help='Clear test table before running'
    )

    args = parser.parse_args()

    # Load config and connect to database
    config = ConfigLoader()
    db = DatabaseManager(config.get_db_path())
    db.connect()

    try:
        runner = TestRunner(db, config)
        runner.run(
            engine_filter=args.engine,
            bookmaker_filter=args.bookmaker,
            limit=args.limit,
            clear_first=args.clear
        )
    finally:
        db.close()


if __name__ == '__main__':
    main()
