"""
Unit tests for snapshot-based change detection.

Tests the get_latest_snapshot_1x2_odds and check_1x2_odds_changed methods
to ensure correct behavior when comparing new odds against market snapshots.
"""

import unittest
import sqlite3
from datetime import datetime
from pathlib import Path
import sys

# Add src to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.db.manager import DatabaseManager


class TestChangeDetection(unittest.TestCase):
    """Test cases for snapshot-based odds change detection."""

    def setUp(self):
        """Set up in-memory database for each test."""
        self.db = DatabaseManager(':memory:')
        self.db.connect()

        # Insert test event
        self.test_event_id = 'sr:match:12345'
        cursor = self.db.conn.cursor()
        cursor.execute("""
            INSERT INTO events (
                sportradar_id, home_team, away_team, start_time,
                tournament_name, created_at
            ) VALUES (?, ?, ?, ?, ?, ?)
        """, (
            self.test_event_id, 'Team A', 'Team B',
            datetime.now().isoformat(), 'Test League',
            datetime.now().isoformat()
        ))
        self.db.conn.commit()

    def tearDown(self):
        """Clean up database connection."""
        self.db.close()

    def _create_snapshot_with_1x2(
        self,
        sportradar_id: str,
        bookmaker: str,
        home_odds: float,
        draw_odds: float,
        away_odds: float,
    ) -> int:
        """
        Helper to create a scraping session and market snapshot with 1X2 odds.

        Args:
            sportradar_id: Event ID
            bookmaker: 'sporty', 'pawa', or 'bet9ja'
            home_odds: Home win odds
            draw_odds: Draw odds
            away_odds: Away win odds

        Returns:
            Session ID
        """
        # Create scraping session
        session_id = self.db.start_match_session(sportradar_id)

        # Prepare outcomes based on bookmaker
        if bookmaker == 'sporty':
            outcomes = [
                {'desc': '1', 'odds': home_odds},
                {'desc': 'X', 'odds': draw_odds},
                {'desc': '2', 'odds': away_odds},
            ]
            self.db.upsert_market_snapshot(
                scraping_history_id=session_id,
                sportradar_id=sportradar_id,
                market_name='1X2',
                specifier='',
                sporty_market_id='1',
                sporty_outcomes=outcomes,
            )
        elif bookmaker == 'pawa':
            outcomes = [
                {'name': 'Home', 'odds': home_odds},
                {'name': 'Draw', 'odds': draw_odds},
                {'name': 'Away', 'odds': away_odds},
            ]
            self.db.upsert_market_snapshot(
                scraping_history_id=session_id,
                sportradar_id=sportradar_id,
                market_name='1X2',
                specifier='',
                pawa_market_id='3743',
                pawa_outcomes=outcomes,
            )
        elif bookmaker == 'bet9ja':
            outcomes = [
                {'desc': '1', 'odds': home_odds},
                {'desc': 'X', 'odds': draw_odds},
                {'desc': '2', 'odds': away_odds},
            ]
            self.db.upsert_market_snapshot(
                scraping_history_id=session_id,
                sportradar_id=sportradar_id,
                market_name='1X2',
                specifier='',
                bet9ja_market_id='S_1X2',
                bet9ja_outcomes=outcomes,
            )

        return session_id

    def test_no_previous_snapshot_returns_true(self):
        """Test that check returns True when no previous snapshot exists (always scrape)."""
        # No snapshot created, so should return True
        changed = self.db.check_1x2_odds_changed(
            sportradar_id=self.test_event_id,
            bookmaker='pawa',
            home_odds=2.10,
            draw_odds=3.20,
            away_odds=3.50,
        )

        self.assertTrue(changed, "Should return True when no previous snapshot exists")

    def test_identical_odds_within_tolerance_returns_false(self):
        """Test that check returns False when odds are identical within tolerance."""
        # Create initial snapshot
        self._create_snapshot_with_1x2(
            sportradar_id=self.test_event_id,
            bookmaker='pawa',
            home_odds=2.10,
            draw_odds=3.20,
            away_odds=3.50,
        )

        # Check with same odds (within tolerance)
        changed = self.db.check_1x2_odds_changed(
            sportradar_id=self.test_event_id,
            bookmaker='pawa',
            home_odds=2.105,  # 0.005 difference (within 0.01 tolerance)
            draw_odds=3.205,
            away_odds=3.505,
        )

        self.assertFalse(changed, "Should return False when odds unchanged within tolerance")

    def test_odds_changed_beyond_tolerance_returns_true(self):
        """Test that check returns True when odds change beyond tolerance."""
        # Create initial snapshot
        self._create_snapshot_with_1x2(
            sportradar_id=self.test_event_id,
            bookmaker='pawa',
            home_odds=2.10,
            draw_odds=3.20,
            away_odds=3.50,
        )

        # Check with significantly different odds
        changed = self.db.check_1x2_odds_changed(
            sportradar_id=self.test_event_id,
            bookmaker='pawa',
            home_odds=2.15,  # 0.05 difference (beyond 0.01 tolerance)
            draw_odds=3.20,
            away_odds=3.50,
        )

        self.assertTrue(changed, "Should return True when odds changed beyond tolerance")

    def test_different_bookmakers_tracked_independently(self):
        """Test that different bookmakers are tracked independently."""
        # Create snapshot for Sportybet
        self._create_snapshot_with_1x2(
            sportradar_id=self.test_event_id,
            bookmaker='sporty',
            home_odds=2.00,
            draw_odds=3.00,
            away_odds=4.00,
        )

        # Check BetPawa (no snapshot for BetPawa yet)
        changed_pawa = self.db.check_1x2_odds_changed(
            sportradar_id=self.test_event_id,
            bookmaker='pawa',
            home_odds=2.10,
            draw_odds=3.20,
            away_odds=3.80,
        )

        # Check Sportybet with same odds
        changed_sporty = self.db.check_1x2_odds_changed(
            sportradar_id=self.test_event_id,
            bookmaker='sporty',
            home_odds=2.00,
            draw_odds=3.00,
            away_odds=4.00,
        )

        self.assertTrue(changed_pawa, "BetPawa should show changed (no snapshot)")
        self.assertFalse(changed_sporty, "Sportybet should show unchanged (same odds)")

    def test_get_latest_snapshot_returns_correct_data(self):
        """Test that get_latest_snapshot_1x2_odds returns the most recent snapshot."""
        # Create first snapshot
        self._create_snapshot_with_1x2(
            sportradar_id=self.test_event_id,
            bookmaker='pawa',
            home_odds=2.00,
            draw_odds=3.00,
            away_odds=4.00,
        )

        # Create second snapshot with different odds
        self._create_snapshot_with_1x2(
            sportradar_id=self.test_event_id,
            bookmaker='pawa',
            home_odds=2.20,
            draw_odds=3.30,
            away_odds=3.70,
        )

        # Get latest snapshot
        odds = self.db.get_latest_snapshot_1x2_odds(
            sportradar_id=self.test_event_id,
            bookmaker='pawa',
        )

        self.assertIsNotNone(odds, "Should return odds tuple")
        self.assertEqual(odds[0], 2.20, "Should return latest home odds")
        self.assertEqual(odds[1], 3.30, "Should return latest draw odds")
        self.assertEqual(odds[2], 3.70, "Should return latest away odds")

    def test_get_latest_snapshot_returns_none_for_no_snapshots(self):
        """Test that get_latest_snapshot_1x2_odds returns None when no snapshots exist."""
        odds = self.db.get_latest_snapshot_1x2_odds(
            sportradar_id=self.test_event_id,
            bookmaker='pawa',
        )

        self.assertIsNone(odds, "Should return None when no snapshots exist")

    def test_multiple_events_tracked_independently(self):
        """Test that different events are tracked independently."""
        # Create second test event
        second_event_id = 'sr:match:67890'
        cursor = self.db.conn.cursor()
        cursor.execute("""
            INSERT INTO events (
                sportradar_id, home_team, away_team, start_time,
                tournament_name, created_at
            ) VALUES (?, ?, ?, ?, ?, ?)
        """, (
            second_event_id, 'Team C', 'Team D',
            datetime.now().isoformat(), 'Test League',
            datetime.now().isoformat()
        ))
        self.db.conn.commit()

        # Create snapshot for first event
        self._create_snapshot_with_1x2(
            sportradar_id=self.test_event_id,
            bookmaker='pawa',
            home_odds=2.00,
            draw_odds=3.00,
            away_odds=4.00,
        )

        # Create snapshot for second event
        self._create_snapshot_with_1x2(
            sportradar_id=second_event_id,
            bookmaker='pawa',
            home_odds=1.80,
            draw_odds=3.50,
            away_odds=4.50,
        )

        # Check first event with same odds
        changed_first = self.db.check_1x2_odds_changed(
            sportradar_id=self.test_event_id,
            bookmaker='pawa',
            home_odds=2.00,
            draw_odds=3.00,
            away_odds=4.00,
        )

        # Check second event with different odds
        changed_second = self.db.check_1x2_odds_changed(
            sportradar_id=second_event_id,
            bookmaker='pawa',
            home_odds=1.90,
            draw_odds=3.50,
            away_odds=4.50,
        )

        self.assertFalse(changed_first, "First event should show unchanged")
        self.assertTrue(changed_second, "Second event should show changed")


if __name__ == '__main__':
    unittest.main()
