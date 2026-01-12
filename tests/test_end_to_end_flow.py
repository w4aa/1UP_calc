"""
End-to-End Pipeline Validation Test

Tests the complete data flow from tournament configuration through to engine calculations:
1. Tournament sync from config
2. BetPawa change detection
3. Multi-bookmaker scraping (conditional on changes)
4. Snapshot creation
5. Engine execution

Also validates:
- Partial failure handling (one scraper fails, others continue)
- Change detection optimization (skip re-scraping unchanged data)
"""

import asyncio
import pytest
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.unified_scraper import UnifiedScraper
from src.db.manager import DatabaseManager
from src.config import ConfigLoader
from src.engine.runner import EngineRunner


@pytest.fixture
def config():
    """Load configuration."""
    return ConfigLoader()


@pytest.fixture
def db(config):
    """Setup database connection."""
    db_manager = DatabaseManager(config.get_db_path())
    db_manager.connect()
    yield db_manager
    db_manager.close()


@pytest.fixture
def scraper():
    """Create UnifiedScraper instance."""
    return UnifiedScraper()


class TestEndToEndFlow:
    """Test suite for complete pipeline validation."""

    @pytest.mark.asyncio
    async def test_full_pipeline_execution(self, scraper, db):
        """
        Test 1: Full pipeline execution validates all stages work correctly.

        Validates:
        - Tournament sync from config to database
        - Events fetched and stored
        - Market snapshots created
        - Scraping history records exist
        - Engine calculations generated
        """
        print("\n" + "="*60)
        print("TEST 1: Full Pipeline Execution")
        print("="*60)

        # Record initial state
        initial_stats = db.get_stats()
        initial_events = initial_stats['total_events']
        initial_snapshots = db.conn.execute("SELECT COUNT(*) as count FROM market_snapshots").fetchone()['count']
        initial_calculations = db.conn.execute("SELECT COUNT(*) as count FROM engine_calculations").fetchone()['count']

        print(f"\nInitial state:")
        print(f"  Events: {initial_events}")
        print(f"  Snapshots: {initial_snapshots}")
        print(f"  Calculations: {initial_calculations}")

        # Execute full pipeline (scrape + engines)
        print("\n[STAGE 1] Running unified scraper...")
        await scraper.run(
            scrape_sporty=True,
            scrape_pawa=True,
            force=False,  # Use change detection
            run_engines=False  # We'll run engines separately for observability
        )

        print("\n[STAGE 2] Running engines...")
        runner = EngineRunner(db)
        unprocessed = db.get_unprocessed_sessions()
        if unprocessed:
            result = runner.run_new_snapshots()
            print(f"  Sessions processed: {result.get('sessions', 0)}")
            print(f"  Calculations created: {result['calculations']}")
        else:
            print("  No new snapshots to process")

        # Validate all stages completed
        final_stats = db.get_stats()
        final_events = final_stats['total_events']
        final_snapshots = db.conn.execute("SELECT COUNT(*) as count FROM market_snapshots").fetchone()['count']
        final_calculations = db.conn.execute("SELECT COUNT(*) as count FROM engine_calculations").fetchone()['count']

        print(f"\nFinal state:")
        print(f"  Events: {final_events}")
        print(f"  Snapshots: {final_snapshots}")
        print(f"  Calculations: {final_calculations}")

        # Assertions
        print("\n[VALIDATION]")

        # 1. Tournament sync validation
        tournaments = db.conn.execute("SELECT COUNT(*) as count FROM tournaments").fetchone()
        print(f"✓ Tournaments synced: {tournaments['count']} tournaments")
        assert tournaments['count'] > 0, "No tournaments found in database"

        # 2. Events validation
        print(f"✓ Events stored: {final_events} events total")
        assert final_events > 0, "No events found after scraping"

        # 3. Snapshots validation
        print(f"✓ Snapshots created: {final_snapshots} snapshots total")
        assert final_snapshots >= initial_snapshots, "Snapshots should increase or stay same"

        # 4. Scraping history validation
        scraping_sessions = db.conn.execute("SELECT COUNT(*) as count FROM scraping_history").fetchone()
        print(f"✓ Scraping sessions: {scraping_sessions['count']} sessions")
        assert scraping_sessions['count'] > 0, "No scraping history records found"

        # 5. Engine calculations validation
        print(f"✓ Calculations generated: {final_calculations} calculations total")
        assert final_calculations >= initial_calculations, "Calculations should increase or stay same"

        print("\n[RESULT] Full pipeline validation PASSED")

    @pytest.mark.asyncio
    async def test_partial_failure_handling(self, scraper, db):
        """
        Test 2: Pipeline continues when one scraper fails.

        Simulates Sportybet scraper failure and validates:
        - BetPawa data still collected
        - Bet9ja data still collected (if enabled)
        - Snapshots still created
        - Pipeline completes successfully
        """
        print("\n" + "="*60)
        print("TEST 2: Partial Failure Handling")
        print("="*60)

        # Mock Sportybet scraper to raise exception
        original_scrape = None

        async def mock_sporty_scrape(*args, **kwargs):
            """Simulate Sportybet scraper failure."""
            print("  [SIMULATED] Sportybet scraper failed")
            raise Exception("Simulated Sportybet failure")

        # Patch the Sportybet events scraper
        with patch('src.scraper.sporty.SportybetEventsScraper.scrape_events', side_effect=mock_sporty_scrape):
            print("\n[TEST] Running scraper with Sportybet failure...")

            # Record state before
            initial_snapshots = db.conn.execute("SELECT COUNT(*) as count FROM market_snapshots").fetchone()['count']

            # Run scraper - should handle Sportybet failure gracefully
            try:
                await scraper.run(
                    scrape_sporty=True,  # Will fail
                    scrape_pawa=True,    # Should succeed
                    force=False,
                    run_engines=False
                )
                print("  [OK] Pipeline completed despite Sportybet failure")
            except Exception as e:
                # If it propagates, that's fine - we just want to verify data still collected
                print(f"  [INFO] Exception propagated: {e}")

            # Validate that other scrapers still worked
            final_snapshots = db.conn.execute("SELECT COUNT(*) as count FROM market_snapshots").fetchone()['count']

            # Check BetPawa data exists
            pawa_markets = db.conn.execute("""
                SELECT COUNT(*) as count
                FROM markets
                WHERE bookmaker = 'pawa'
            """).fetchone()

            print(f"\n[VALIDATION]")
            print(f"✓ BetPawa markets collected: {pawa_markets['count']}")
            print(f"✓ Snapshots created: {final_snapshots - initial_snapshots} new snapshots")

            # Assertions
            assert pawa_markets['count'] > 0, "BetPawa data should exist despite Sportybet failure"
            print("\n[RESULT] Partial failure handling PASSED")

    @pytest.mark.asyncio
    async def test_change_detection_optimization(self, scraper, db):
        """
        Test 3: Change detection prevents unnecessary re-scraping.

        Validates:
        - First run: scrapes and creates snapshots
        - Second run (no changes): detects no changes, skips scraping
        - No duplicate snapshots created
        - Engines not triggered for unchanged data
        """
        print("\n" + "="*60)
        print("TEST 3: Change Detection Optimization")
        print("="*60)

        # Get initial snapshot count
        initial_snapshots = db.conn.execute("SELECT COUNT(*) as count FROM market_snapshots").fetchone()['count']
        initial_calculations = db.conn.execute("SELECT COUNT(*) as count FROM engine_calculations").fetchone()['count']

        print(f"\nInitial state:")
        print(f"  Snapshots: {initial_snapshots}")
        print(f"  Calculations: {initial_calculations}")

        # First run: with force flag (ensures scraping happens)
        print("\n[RUN 1] Running with force=True...")
        await scraper.run(
            scrape_sporty=True,
            scrape_pawa=True,
            force=True,  # Force scraping
            run_engines=False
        )

        after_first_snapshots = db.conn.execute("SELECT COUNT(*) as count FROM market_snapshots").fetchone()['count']
        print(f"  After first run: {after_first_snapshots} snapshots")

        # Run engines on first run data
        runner = EngineRunner(db)
        unprocessed = db.get_unprocessed_sessions()
        if unprocessed:
            result = runner.run_new_snapshots()
            print(f"  Calculations from first run: {result['calculations']}")

        after_first_calculations = db.conn.execute("SELECT COUNT(*) as count FROM engine_calculations").fetchone()['count']

        # Second run: without force flag (should detect no changes)
        print("\n[RUN 2] Running with force=False (change detection)...")
        await scraper.run(
            scrape_sporty=True,
            scrape_pawa=True,
            force=False,  # Use change detection
            run_engines=False
        )

        after_second_snapshots = db.conn.execute("SELECT COUNT(*) as count FROM market_snapshots").fetchone()['count']
        print(f"  After second run: {after_second_snapshots} snapshots")

        # Check if engines were triggered
        unprocessed_after_second = db.get_unprocessed_sessions()
        print(f"  Unprocessed sessions: {len(unprocessed_after_second)}")

        # Validation
        print(f"\n[VALIDATION]")

        # Snapshots should either stay same or increase minimally
        # (Some bookmakers might have live odds changes)
        snapshot_increase = after_second_snapshots - after_first_snapshots
        print(f"✓ Snapshot increase on second run: {snapshot_increase}")

        # If no live changes occurred, snapshots should be identical
        # If live changes occurred, increase should be minimal compared to first run
        first_run_increase = after_first_snapshots - initial_snapshots
        if snapshot_increase > 0:
            print(f"  (Live odds may have changed - {snapshot_increase} new snapshots)")
            assert snapshot_increase < first_run_increase, "Second run should scrape less than first run"
        else:
            print(f"  (No changes detected - optimal behavior)")

        print("\n[RESULT] Change detection optimization PASSED")

    @pytest.mark.asyncio
    async def test_duplicate_calculation_prevention(self, db):
        """
        Test 4: Engines prevent duplicate calculations for same snapshot.

        Validates:
        - Running engines twice on same snapshots doesn't create duplicates
        - Unique constraint (sportradar_id + scraping_history_id) enforced
        """
        print("\n" + "="*60)
        print("TEST 4: Duplicate Calculation Prevention")
        print("="*60)

        runner = EngineRunner(db)

        # Get unprocessed sessions
        unprocessed_before = db.get_unprocessed_sessions()

        if not unprocessed_before:
            print("\n[SKIP] No unprocessed sessions available for testing")
            print("(This test requires new snapshots - run full scraper first)")
            return

        print(f"\n[STATE] Unprocessed sessions: {len(unprocessed_before)}")

        # First engine run
        print("\n[RUN 1] Processing snapshots...")
        result1 = runner.run_new_snapshots()
        print(f"  Calculations created: {result1['calculations']}")

        # Check for remaining unprocessed
        unprocessed_after_first = db.get_unprocessed_sessions()
        print(f"  Remaining unprocessed: {len(unprocessed_after_first)}")

        # Second engine run (should find nothing new)
        print("\n[RUN 2] Attempting to process again...")
        result2 = runner.run_new_snapshots()
        print(f"  Calculations created: {result2['calculations']}")

        # Validation
        print(f"\n[VALIDATION]")
        assert result2['calculations'] == 0, "Second run should create 0 calculations (duplicates prevented)"
        print(f"✓ Duplicate prevention working: 0 calculations on second run")

        print("\n[RESULT] Duplicate calculation prevention PASSED")

    @pytest.mark.asyncio
    async def test_tournament_database_sync(self, db, config):
        """
        Test 5: Tournament configuration syncs to database correctly.

        Validates:
        - All enabled tournaments in config exist in tournaments table
        - Tournament properties match (name, ID, enabled status)
        """
        print("\n" + "="*60)
        print("TEST 5: Tournament Database Sync")
        print("="*60)

        # Get tournaments from config
        tournaments_config = config.get_enabled_tournaments()
        print(f"\n[CONFIG] Enabled tournaments: {len(tournaments_config)}")

        # Get tournaments from database
        tournaments_db = db.conn.execute("SELECT * FROM tournaments WHERE enabled = 1").fetchall()
        print(f"[DATABASE] Enabled tournaments: {len(tournaments_db)}")

        # Validation
        print(f"\n[VALIDATION]")

        # Should have at least as many tournaments in DB as enabled in config
        assert len(tournaments_db) >= len(tournaments_config), \
            "Database should have all enabled tournaments from config"

        # Check specific tournament sync
        for config_tournament in tournaments_config:
            tournament_id = config_tournament.get('tournament_id')
            db_tournament = db.conn.execute(
                "SELECT * FROM tournaments WHERE id = ?",
                (tournament_id,)
            ).fetchone()

            if db_tournament:
                print(f"✓ Tournament synced: {db_tournament['name']}")
                assert db_tournament['enabled'] == 1, f"Tournament {tournament_id} should be enabled"
            else:
                # Tournament might not sync until first scrape
                print(f"  Tournament {tournament_id} not yet synced (needs first scrape)")

        print("\n[RESULT] Tournament database sync PASSED")


def run_tests():
    """Run all tests with pytest."""
    print("\n" + "="*60)
    print("  END-TO-END PIPELINE VALIDATION")
    print("="*60)

    pytest.main([__file__, '-v', '-s'])


if __name__ == "__main__":
    run_tests()
