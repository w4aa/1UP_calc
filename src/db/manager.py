"""
Database manager for unified betting scraper.
Handles all SQLite operations for events and markets.
"""

import sqlite3
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class DatabaseManager:
    """
    Manages SQLite database for storing events and markets from both bookmakers.
    """

    def __init__(self, db_path: str):
        """
        Initialize database manager.
        
        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn: Optional[sqlite3.Connection] = None
        
    def connect(self) -> sqlite3.Connection:
        """Connect to database and create tables if needed."""
        self.conn = sqlite3.connect(str(self.db_path))
        self.conn.row_factory = sqlite3.Row
        self._create_tables()
        logger.info(f"Connected to database: {self.db_path}")
        return self.conn
    
    def close(self):
        """Close database connection."""
        if self.conn:
            self.conn.close()
            self.conn = None
            logger.info("Database connection closed")
    
    def _create_tables(self):
        """Create database tables if they don't exist."""
        cursor = self.conn.cursor()
        
        # Tournaments table - track configured tournaments
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS tournaments (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                sport TEXT DEFAULT 'football',
                category_id TEXT,
                pawa_category_id TEXT,
                pawa_competition_id TEXT,
                enabled INTEGER DEFAULT 1,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Scraping history table - track scraping sessions per MATCH
        # Each session represents one scrape of a match (both bookmakers together)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS scraping_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sportradar_id TEXT NOT NULL,
                tournament_id TEXT,
                scraped_at TEXT NOT NULL,
                status TEXT DEFAULT 'completed',
                FOREIGN KEY (sportradar_id) REFERENCES events(sportradar_id),
                FOREIGN KEY (tournament_id) REFERENCES tournaments(id)
            )
        """)
        
        # Events table - unified storage for both bookmakers
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS events (
                sportradar_id TEXT PRIMARY KEY,
                home_team TEXT NOT NULL,
                away_team TEXT NOT NULL,
                start_time TEXT NOT NULL,
                tournament_name TEXT,
                
                -- Sportybet data
                sporty_event_id TEXT,
                sporty_tournament_id TEXT,
                sporty_market_count INTEGER DEFAULT 0,
                sporty_scraped_at TEXT,
                
                -- Betpawa data
                pawa_event_id TEXT,
                pawa_competition_id TEXT,
                pawa_market_count INTEGER DEFAULT 0,
                pawa_scraped_at TEXT,
                
                -- 1X2 odds cache for change detection
                sporty_1x2_home REAL,
                sporty_1x2_draw REAL,
                sporty_1x2_away REAL,
                pawa_1x2_home REAL,
                pawa_1x2_draw REAL,
                pawa_1x2_away REAL,
                
                -- Status
                matched INTEGER DEFAULT 0,
                needs_rescrape INTEGER DEFAULT 0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Markets table - unified odds from both bookmakers (LATEST snapshot)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS markets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sportradar_id TEXT NOT NULL,
                
                -- Market identification
                market_name TEXT NOT NULL,
                specifier TEXT NOT NULL DEFAULT '',
                
                -- Sportybet odds
                sporty_market_id TEXT,
                sporty_outcome_1_name TEXT,
                sporty_outcome_1_odds REAL,
                sporty_outcome_2_name TEXT,
                sporty_outcome_2_odds REAL,
                sporty_outcome_3_name TEXT,
                sporty_outcome_3_odds REAL,
                
                -- Betpawa odds
                pawa_market_id TEXT,
                pawa_outcome_1_name TEXT,
                pawa_outcome_1_odds REAL,
                pawa_outcome_2_name TEXT,
                pawa_outcome_2_odds REAL,
                pawa_outcome_3_name TEXT,
                pawa_outcome_3_odds REAL,

                -- Bet9ja odds
                bet9ja_market_id TEXT,
                bet9ja_outcome_1_name TEXT,
                bet9ja_outcome_1_odds REAL,
                bet9ja_outcome_2_name TEXT,
                bet9ja_outcome_2_odds REAL,
                bet9ja_outcome_3_name TEXT,
                bet9ja_outcome_3_odds REAL,

                -- Metadata
                scraped_at TEXT DEFAULT CURRENT_TIMESTAMP,
                
                FOREIGN KEY (sportradar_id) REFERENCES events(sportradar_id),
                UNIQUE(sportradar_id, market_name, specifier)
            )
        """)
        
        # Market snapshots table - historical odds linked to scraping sessions
        # Mirrors markets table structure: both bookmakers in one row
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS market_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                scraping_history_id INTEGER NOT NULL,
                sportradar_id TEXT NOT NULL,
                
                -- Market identification
                market_name TEXT NOT NULL,
                specifier TEXT NOT NULL DEFAULT '',
                
                -- Sportybet odds
                sporty_market_id TEXT,
                sporty_outcome_1_name TEXT,
                sporty_outcome_1_odds REAL,
                sporty_outcome_2_name TEXT,
                sporty_outcome_2_odds REAL,
                sporty_outcome_3_name TEXT,
                sporty_outcome_3_odds REAL,
                
                -- Betpawa odds
                pawa_market_id TEXT,
                pawa_outcome_1_name TEXT,
                pawa_outcome_1_odds REAL,
                pawa_outcome_2_name TEXT,
                pawa_outcome_2_odds REAL,
                pawa_outcome_3_name TEXT,
                pawa_outcome_3_odds REAL,
                
                -- Bet9ja odds
                bet9ja_market_id TEXT,
                bet9ja_outcome_1_name TEXT,
                bet9ja_outcome_1_odds REAL,
                bet9ja_outcome_2_name TEXT,
                bet9ja_outcome_2_odds REAL,
                bet9ja_outcome_3_name TEXT,
                bet9ja_outcome_3_odds REAL,
                
                FOREIGN KEY (scraping_history_id) REFERENCES scraping_history(id),
                FOREIGN KEY (sportradar_id) REFERENCES events(sportradar_id),
                UNIQUE(scraping_history_id, sportradar_id, market_name, specifier)
            )
        """)
        
        # Create indexes for faster lookups
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_events_start_time 
            ON events(start_time)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_events_matched 
            ON events(matched)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_markets_sportradar 
            ON markets(sportradar_id)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_markets_name 
            ON markets(market_name)
        """)
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_snapshots_scraping_history 
            ON market_snapshots(scraping_history_id)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_snapshots_event 
            ON market_snapshots(sportradar_id)
        """)
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_scraping_history_event 
            ON scraping_history(sportradar_id)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_scraping_history_scraped_at 
            ON scraping_history(scraped_at)
        """)
        
        # Engine calculations table - stores 1UP pricing from all engines
        # Links to scraping_history for historical tracking
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS engine_calculations (
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
                
                -- Actual Sportybet 1UP odds (for comparison)
                actual_home REAL,
                actual_away REAL,
                actual_draw REAL,
                
                -- Metadata
                calculated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                
                FOREIGN KEY (sportradar_id) REFERENCES events(sportradar_id),
                FOREIGN KEY (scraping_history_id) REFERENCES scraping_history(id)
            )
        """)
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_engine_calcs_event 
            ON engine_calculations(sportradar_id)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_engine_calcs_engine 
            ON engine_calculations(engine_name, bookmaker)
        """)
        
        self.conn.commit()
        
        # Run migrations to add new columns to existing tables
        self._run_migrations()
        
        # Create indexes that depend on migrated columns
        self._create_post_migration_indexes()
        
        logger.debug("Database tables created/verified")
    
    def _create_post_migration_indexes(self):
        """Create indexes on columns that may have been added by migrations."""
        cursor = self.conn.cursor()
        
        # Check if scraping_history_id column exists before creating index
        cursor.execute("PRAGMA table_info(engine_calculations)")
        ec_columns = {row[1] for row in cursor.fetchall()}
        
        if 'scraping_history_id' in ec_columns:
            try:
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_engine_calcs_history 
                    ON engine_calculations(scraping_history_id)
                """)
            except Exception:
                pass
        
        self.conn.commit()
    
    def _run_migrations(self):
        """Run migrations to add new columns if they don't exist."""
        cursor = self.conn.cursor()
        
        # Get existing columns in events table
        cursor.execute("PRAGMA table_info(events)")
        existing_columns = {row[1] for row in cursor.fetchall()}
        
        # Add 1X2 odds columns if missing
        new_columns = [
            ("sporty_1x2_home", "REAL"),
            ("sporty_1x2_draw", "REAL"),
            ("sporty_1x2_away", "REAL"),
            ("pawa_1x2_home", "REAL"),
            ("pawa_1x2_draw", "REAL"),
            ("pawa_1x2_away", "REAL"),
            ("needs_rescrape", "INTEGER DEFAULT 0"),
            ("bet9ja_event_id", "TEXT"),
            ("bet9ja_group_id", "TEXT"),
            ("bet9ja_market_count", "INTEGER DEFAULT 0"),
            ("bet9ja_scraped_at", "TEXT"),
        ]
        
        for col_name, col_type in new_columns:
            if col_name not in existing_columns:
                try:
                    cursor.execute(f"ALTER TABLE events ADD COLUMN {col_name} {col_type}")
                    logger.info(f"Added column events.{col_name}")
                except Exception as e:
                    logger.debug(f"Column {col_name} may already exist: {e}")
        
        # Add scraping_history_id to engine_calculations if missing
        cursor.execute("PRAGMA table_info(engine_calculations)")
        ec_columns = {row[1] for row in cursor.fetchall()}
        
        if 'scraping_history_id' not in ec_columns:
            try:
                cursor.execute("ALTER TABLE engine_calculations ADD COLUMN scraping_history_id INTEGER")
                logger.info("Added column engine_calculations.scraping_history_id")
            except Exception as e:
                logger.debug(f"Column scraping_history_id may already exist: {e}")
        
        # Add columns to store actual 1UP odds from both Sportybet and Bet9ja
        new_ec_cols = [
            ("actual_sporty_home", "REAL"),
            ("actual_sporty_draw", "REAL"),
            ("actual_sporty_away", "REAL"),
            ("actual_bet9ja_home", "REAL"),
            ("actual_bet9ja_draw", "REAL"),
            ("actual_bet9ja_away", "REAL"),
        ]
        for col_name, col_type in new_ec_cols:
            if col_name not in ec_columns:
                try:
                    cursor.execute(f"ALTER TABLE engine_calculations ADD COLUMN {col_name} {col_type}")
                    logger.info(f"Added column engine_calculations.{col_name}")
                except Exception as e:
                    logger.debug(f"Column {col_name} may already exist: {e}")
        
        self.conn.commit()

        # Add Bet9ja columns to markets table if missing
        cursor.execute("PRAGMA table_info(markets)")
        markets_columns = {row[1] for row in cursor.fetchall()}
        market_new_cols = [
            ("bet9ja_market_id", "TEXT"),
            ("bet9ja_outcome_1_name", "TEXT"),
            ("bet9ja_outcome_1_odds", "REAL"),
            ("bet9ja_outcome_2_name", "TEXT"),
            ("bet9ja_outcome_2_odds", "REAL"),
            ("bet9ja_outcome_3_name", "TEXT"),
            ("bet9ja_outcome_3_odds", "REAL"),
        ]
        for col_name, col_type in market_new_cols:
            if col_name not in markets_columns:
                try:
                    cursor.execute(f"ALTER TABLE markets ADD COLUMN {col_name} {col_type}")
                    logger.info(f"Added column markets.{col_name}")
                except Exception as e:
                    logger.debug(f"Column markets.{col_name} may already exist: {e}")

        # Add Bet9ja columns to market_snapshots table if missing
        cursor.execute("PRAGMA table_info(market_snapshots)")
        snaps_columns = {row[1] for row in cursor.fetchall()}
        for col_name, col_type in market_new_cols:
            if col_name not in snaps_columns:
                try:
                    cursor.execute(f"ALTER TABLE market_snapshots ADD COLUMN {col_name} {col_type}")
                    logger.info(f"Added column market_snapshots.{col_name}")
                except Exception as e:
                    logger.debug(f"Column market_snapshots.{col_name} may already exist: {e}")

        self.conn.commit()
    
    # ==========================================
    # Tournament Operations
    # ==========================================
    
    def upsert_tournament(
        self,
        tournament_id: str,
        name: str,
        sport: str = "football",
        category_id: str = None,
        pawa_category_id: str = None,
        pawa_competition_id: str = None,
        enabled: bool = True,
    ):
        """Insert or update a tournament."""
        cursor = self.conn.cursor()
        now = datetime.now().isoformat()
        
        cursor.execute("""
            INSERT INTO tournaments (
                id, name, sport, category_id, pawa_category_id, 
                pawa_competition_id, enabled, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                name = excluded.name,
                sport = excluded.sport,
                category_id = excluded.category_id,
                pawa_category_id = excluded.pawa_category_id,
                pawa_competition_id = excluded.pawa_competition_id,
                enabled = excluded.enabled,
                updated_at = excluded.updated_at
        """, (
            tournament_id, name, sport, category_id, pawa_category_id,
            pawa_competition_id, 1 if enabled else 0, now, now
        ))
        self.conn.commit()
    
    def get_tournament(self, tournament_id: str) -> Optional[dict]:
        """Get a tournament by ID."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM tournaments WHERE id = ?", (tournament_id,))
        row = cursor.fetchone()
        return dict(row) if row else None
    
    def get_all_tournaments(self) -> list[dict]:
        """Get all tournaments."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM tournaments ORDER BY name")
        return [dict(row) for row in cursor.fetchall()]
    
    # ==========================================
    # Scraping History Operations (Match-based)
    # ==========================================
    
    def start_match_session(
        self,
        sportradar_id: str,
        tournament_id: str = None,
    ) -> int:
        """
        Start a new scraping session for a match.
        Each session represents one snapshot of a match (both bookmakers).
        
        Args:
            sportradar_id: The match ID
            tournament_id: Optional tournament ID for reference
            
        Returns:
            Session ID
        """
        cursor = self.conn.cursor()
        now = datetime.now().isoformat()
        
        cursor.execute("""
            INSERT INTO scraping_history (
                sportradar_id, tournament_id, scraped_at, status
            ) VALUES (?, ?, ?, 'completed')
        """, (sportradar_id, tournament_id, now))
        
        self.conn.commit()
        return cursor.lastrowid
    
    def get_match_sessions(self, sportradar_id: str) -> list[dict]:
        """Get all scraping sessions for a match (history of snapshots)."""
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT * FROM scraping_history 
            WHERE sportradar_id = ?
            ORDER BY scraped_at DESC
        """, (sportradar_id,))
        return [dict(row) for row in cursor.fetchall()]
    
    def get_latest_match_session(self, sportradar_id: str) -> Optional[dict]:
        """Get the most recent scraping session for a match."""
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT * FROM scraping_history 
            WHERE sportradar_id = ?
            ORDER BY scraped_at DESC LIMIT 1
        """, (sportradar_id,))
        row = cursor.fetchone()
        return dict(row) if row else None
    
    def get_scraping_history(self, limit: int = 50) -> list[dict]:
        """Get recent scraping history with event details."""
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT sh.*, e.home_team, e.away_team, e.tournament_name
            FROM scraping_history sh
            LEFT JOIN events e ON sh.sportradar_id = e.sportradar_id
            ORDER BY sh.scraped_at DESC
            LIMIT ?
        """, (limit,))
        return [dict(row) for row in cursor.fetchall()]
    
    # ==========================================
    # Event Operations
    # ==========================================
    
    def upsert_sporty_event(
        self,
        sportradar_id: str,
        home_team: str,
        away_team: str,
        start_time: datetime,
        tournament_name: str,
        sporty_event_id: str,
        sporty_tournament_id: str,
        market_count: int = 0,
    ):
        """Insert or update a Sportybet event."""
        cursor = self.conn.cursor()
        now = datetime.now().isoformat()
        
        cursor.execute("""
            INSERT INTO events (
                sportradar_id, home_team, away_team, start_time, tournament_name,
                sporty_event_id, sporty_tournament_id, sporty_market_count,
                sporty_scraped_at, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(sportradar_id) DO UPDATE SET
                sporty_event_id = excluded.sporty_event_id,
                sporty_tournament_id = excluded.sporty_tournament_id,
                sporty_market_count = excluded.sporty_market_count,
                sporty_scraped_at = excluded.sporty_scraped_at,
                updated_at = excluded.updated_at
        """, (
            sportradar_id, home_team, away_team,
            start_time.isoformat() if isinstance(start_time, datetime) else start_time,
            tournament_name, sporty_event_id, sporty_tournament_id,
            market_count, now, now, now
        ))
        
        self._update_matched_status(sportradar_id)
        self.conn.commit()
    
    def upsert_pawa_event(
        self,
        sportradar_id: str,
        home_team: str,
        away_team: str,
        start_time: datetime,
        tournament_name: str,
        pawa_event_id: str,
        pawa_competition_id: str,
        market_count: int = 0,
    ):
        """Insert or update a Betpawa event."""
        cursor = self.conn.cursor()
        now = datetime.now().isoformat()
        
        cursor.execute("""
            INSERT INTO events (
                sportradar_id, home_team, away_team, start_time, tournament_name,
                pawa_event_id, pawa_competition_id, pawa_market_count,
                pawa_scraped_at, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(sportradar_id) DO UPDATE SET
                pawa_event_id = excluded.pawa_event_id,
                pawa_competition_id = excluded.pawa_competition_id,
                pawa_market_count = excluded.pawa_market_count,
                pawa_scraped_at = excluded.pawa_scraped_at,
                updated_at = excluded.updated_at
        """, (
            sportradar_id, home_team, away_team,
            start_time.isoformat() if isinstance(start_time, datetime) else start_time,
            tournament_name, pawa_event_id, pawa_competition_id,
            market_count, now, now, now
        ))
        
        self._update_matched_status(sportradar_id)
        self.conn.commit()

    def upsert_bet9ja_event(
        self,
        sportradar_id: str,
        home_team: str,
        away_team: str,
        start_time: datetime,
        tournament_name: str,
        bet9ja_event_id: str,
        bet9ja_group_id: str,
        market_count: int = 0,
    ):
        """Insert or update a Bet9ja event."""
        cursor = self.conn.cursor()
        now = datetime.now().isoformat()

        cursor.execute("""
            INSERT INTO events (
                sportradar_id, home_team, away_team, start_time, tournament_name,
                bet9ja_event_id, bet9ja_group_id, bet9ja_market_count,
                bet9ja_scraped_at, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(sportradar_id) DO UPDATE SET
                bet9ja_event_id = excluded.bet9ja_event_id,
                bet9ja_group_id = excluded.bet9ja_group_id,
                bet9ja_market_count = excluded.bet9ja_market_count,
                bet9ja_scraped_at = excluded.bet9ja_scraped_at,
                updated_at = excluded.updated_at
        """, (
            sportradar_id, home_team, away_team,
            start_time.isoformat() if isinstance(start_time, datetime) else start_time,
            tournament_name, bet9ja_event_id, bet9ja_group_id,
            market_count, now, now, now
        ))

        self._update_matched_status(sportradar_id)
        self.conn.commit()
    
    def _update_matched_status(self, sportradar_id: str):
        """Update matched status based on whether both bookmakers have data."""
        cursor = self.conn.cursor()
        cursor.execute("""
            UPDATE events 
            SET matched = (
                sporty_event_id IS NOT NULL AND (
                    pawa_event_id IS NOT NULL OR bet9ja_event_id IS NOT NULL
                )
            )
            WHERE sportradar_id = ?
        """, (sportradar_id,))
    
    def check_1x2_odds_changed(
        self,
        sportradar_id: str,
        bookmaker: str,
        home_odds: float,
        draw_odds: float,
        away_odds: float,
        tolerance: float = 0.01,
    ) -> bool:
        """
        Check if 1X2 odds have changed for an event.
        
        Args:
            sportradar_id: Event ID
            bookmaker: 'sporty' or 'pawa'
            home_odds: New home win odds
            draw_odds: New draw odds
            away_odds: New away win odds
            tolerance: Minimum change to consider as changed
            
        Returns:
            True if odds changed, False if same
        """
        cursor = self.conn.cursor()
        
        if bookmaker == "sporty":
            cursor.execute("""
                SELECT sporty_1x2_home, sporty_1x2_draw, sporty_1x2_away
                FROM events WHERE sportradar_id = ?
            """, (sportradar_id,))
        else:
            cursor.execute("""
                SELECT pawa_1x2_home, pawa_1x2_draw, pawa_1x2_away
                FROM events WHERE sportradar_id = ?
            """, (sportradar_id,))
        
        row = cursor.fetchone()
        if not row:
            return True  # New event, always scrape
        
        old_home, old_draw, old_away = row
        
        # If no previous odds, consider changed
        if old_home is None or old_draw is None or old_away is None:
            return True
        
        # Check if any odds changed beyond tolerance
        if (abs(home_odds - old_home) > tolerance or
            abs(draw_odds - old_draw) > tolerance or
            abs(away_odds - old_away) > tolerance):
            return True
        
        return False
    
    def update_1x2_odds(
        self,
        sportradar_id: str,
        bookmaker: str,
        home_odds: float,
        draw_odds: float,
        away_odds: float,
    ):
        """Update cached 1X2 odds for an event."""
        cursor = self.conn.cursor()
        now = datetime.now().isoformat()
        
        if bookmaker == "sporty":
            cursor.execute("""
                UPDATE events SET
                    sporty_1x2_home = ?,
                    sporty_1x2_draw = ?,
                    sporty_1x2_away = ?,
                    updated_at = ?
                WHERE sportradar_id = ?
            """, (home_odds, draw_odds, away_odds, now, sportradar_id))
        else:
            cursor.execute("""
                UPDATE events SET
                    pawa_1x2_home = ?,
                    pawa_1x2_draw = ?,
                    pawa_1x2_away = ?,
                    updated_at = ?
                WHERE sportradar_id = ?
            """, (home_odds, draw_odds, away_odds, now, sportradar_id))
        
        self.conn.commit()
    
    def get_events_needing_rescrape(self, tournament_id: str = None) -> list[dict]:
        """Get events that need to be re-scraped (odds changed)."""
        cursor = self.conn.cursor()
        
        if tournament_id:
            cursor.execute("""
                SELECT * FROM events 
                WHERE needs_rescrape = 1 AND sporty_tournament_id = ?
                ORDER BY start_time
            """, (tournament_id,))
        else:
            cursor.execute("""
                SELECT * FROM events 
                WHERE needs_rescrape = 1
                ORDER BY start_time
            """)
        
        return [dict(row) for row in cursor.fetchall()]
    
    def mark_event_for_rescrape(self, sportradar_id: str, needs_rescrape: bool = True):
        """Mark an event as needing re-scrape."""
        cursor = self.conn.cursor()
        cursor.execute("""
            UPDATE events SET needs_rescrape = ? WHERE sportradar_id = ?
        """, (1 if needs_rescrape else 0, sportradar_id))
        self.conn.commit()
    
    def get_matched_events(self) -> list[dict]:
        """Get all events that have data from both bookmakers."""
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT * FROM events WHERE matched = 1 ORDER BY start_time
        """)
        return [dict(row) for row in cursor.fetchall()]
    
    def get_all_events(self) -> list[dict]:
        """Get all events."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM events ORDER BY start_time")
        return [dict(row) for row in cursor.fetchall()]
    
    def get_event(self, sportradar_id: str) -> Optional[dict]:
        """Get a single event by Sportradar ID."""
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT * FROM events WHERE sportradar_id = ?", 
            (sportradar_id,)
        )
        row = cursor.fetchone()
        return dict(row) if row else None
    
    # ==========================================
    # Market Operations
    # ==========================================
    
    def upsert_market(
        self,
        sportradar_id: str,
        market_name: str,
        specifier: str = "",
        sporty_market_id: str = None,
        sporty_outcomes: list = None,
        pawa_market_id: str = None,
        pawa_outcomes: list = None,
        bet9ja_market_id: str = None,
        bet9ja_outcomes: list = None,
    ):
        """Insert or update a market with odds from one or both bookmakers."""
        cursor = self.conn.cursor()
        now = datetime.now().isoformat()
        
        # Parse Sportybet outcomes
        s_o1_name, s_o1_odds = None, None
        s_o2_name, s_o2_odds = None, None
        s_o3_name, s_o3_odds = None, None
        
        if sporty_outcomes:
            if len(sporty_outcomes) > 0:
                s_o1_name = sporty_outcomes[0].get("desc")
                s_o1_odds = float(sporty_outcomes[0].get("odds", 0)) if sporty_outcomes[0].get("odds") else None
            if len(sporty_outcomes) > 1:
                s_o2_name = sporty_outcomes[1].get("desc")
                s_o2_odds = float(sporty_outcomes[1].get("odds", 0)) if sporty_outcomes[1].get("odds") else None
            if len(sporty_outcomes) > 2:
                s_o3_name = sporty_outcomes[2].get("desc")
                s_o3_odds = float(sporty_outcomes[2].get("odds", 0)) if sporty_outcomes[2].get("odds") else None
        
        # Parse Pawa outcomes
        p_o1_name, p_o1_odds = None, None
        p_o2_name, p_o2_odds = None, None
        p_o3_name, p_o3_odds = None, None
        
        if pawa_outcomes:
            if len(pawa_outcomes) > 0:
                p_o1_name = pawa_outcomes[0].get("name")
                p_o1_odds = pawa_outcomes[0].get("odds")
            if len(pawa_outcomes) > 1:
                p_o2_name = pawa_outcomes[1].get("name")
                p_o2_odds = pawa_outcomes[1].get("odds")
            if len(pawa_outcomes) > 2:
                p_o3_name = pawa_outcomes[2].get("name")
                p_o3_odds = pawa_outcomes[2].get("odds")

        # Parse Bet9ja outcomes
        b_o1_name, b_o1_odds = None, None
        b_o2_name, b_o2_odds = None, None
        b_o3_name, b_o3_odds = None, None

        if bet9ja_outcomes:
            if len(bet9ja_outcomes) > 0:
                b_o1_name = bet9ja_outcomes[0].get("desc") or bet9ja_outcomes[0].get("name")
                try:
                    b_o1_odds = float(bet9ja_outcomes[0].get("odds", 0)) if bet9ja_outcomes[0].get("odds") else None
                except Exception:
                    b_o1_odds = None
            if len(bet9ja_outcomes) > 1:
                b_o2_name = bet9ja_outcomes[1].get("desc") or bet9ja_outcomes[1].get("name")
                try:
                    b_o2_odds = float(bet9ja_outcomes[1].get("odds", 0)) if bet9ja_outcomes[1].get("odds") else None
                except Exception:
                    b_o2_odds = None
            if len(bet9ja_outcomes) > 2:
                b_o3_name = bet9ja_outcomes[2].get("desc") or bet9ja_outcomes[2].get("name")
                try:
                    b_o3_odds = float(bet9ja_outcomes[2].get("odds", 0)) if bet9ja_outcomes[2].get("odds") else None
                except Exception:
                    b_o3_odds = None
        
        cursor.execute("""
            INSERT INTO markets (
                sportradar_id, market_name, specifier,
                sporty_market_id, sporty_outcome_1_name, sporty_outcome_1_odds,
                sporty_outcome_2_name, sporty_outcome_2_odds,
                sporty_outcome_3_name, sporty_outcome_3_odds,
                pawa_market_id, pawa_outcome_1_name, pawa_outcome_1_odds,
                pawa_outcome_2_name, pawa_outcome_2_odds,
                pawa_outcome_3_name, pawa_outcome_3_odds,
                bet9ja_market_id, bet9ja_outcome_1_name, bet9ja_outcome_1_odds,
                bet9ja_outcome_2_name, bet9ja_outcome_2_odds, bet9ja_outcome_3_name, bet9ja_outcome_3_odds,
                scraped_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(sportradar_id, market_name, specifier) DO UPDATE SET
                sporty_market_id = COALESCE(excluded.sporty_market_id, markets.sporty_market_id),
                sporty_outcome_1_name = COALESCE(excluded.sporty_outcome_1_name, markets.sporty_outcome_1_name),
                sporty_outcome_1_odds = COALESCE(excluded.sporty_outcome_1_odds, markets.sporty_outcome_1_odds),
                sporty_outcome_2_name = COALESCE(excluded.sporty_outcome_2_name, markets.sporty_outcome_2_name),
                sporty_outcome_2_odds = COALESCE(excluded.sporty_outcome_2_odds, markets.sporty_outcome_2_odds),
                sporty_outcome_3_name = COALESCE(excluded.sporty_outcome_3_name, markets.sporty_outcome_3_name),
                sporty_outcome_3_odds = COALESCE(excluded.sporty_outcome_3_odds, markets.sporty_outcome_3_odds),
                pawa_market_id = COALESCE(excluded.pawa_market_id, markets.pawa_market_id),
                pawa_outcome_1_name = COALESCE(excluded.pawa_outcome_1_name, markets.pawa_outcome_1_name),
                pawa_outcome_1_odds = COALESCE(excluded.pawa_outcome_1_odds, markets.pawa_outcome_1_odds),
                pawa_outcome_2_name = COALESCE(excluded.pawa_outcome_2_name, markets.pawa_outcome_2_name),
                pawa_outcome_2_odds = COALESCE(excluded.pawa_outcome_2_odds, markets.pawa_outcome_2_odds),
                pawa_outcome_3_name = COALESCE(excluded.pawa_outcome_3_name, markets.pawa_outcome_3_name),
                pawa_outcome_3_odds = COALESCE(excluded.pawa_outcome_3_odds, markets.pawa_outcome_3_odds),
                bet9ja_market_id = COALESCE(excluded.bet9ja_market_id, markets.bet9ja_market_id),
                bet9ja_outcome_1_name = COALESCE(excluded.bet9ja_outcome_1_name, markets.bet9ja_outcome_1_name),
                bet9ja_outcome_1_odds = COALESCE(excluded.bet9ja_outcome_1_odds, markets.bet9ja_outcome_1_odds),
                bet9ja_outcome_2_name = COALESCE(excluded.bet9ja_outcome_2_name, markets.bet9ja_outcome_2_name),
                bet9ja_outcome_2_odds = COALESCE(excluded.bet9ja_outcome_2_odds, markets.bet9ja_outcome_2_odds),
                bet9ja_outcome_3_name = COALESCE(excluded.bet9ja_outcome_3_name, markets.bet9ja_outcome_3_name),
                bet9ja_outcome_3_odds = COALESCE(excluded.bet9ja_outcome_3_odds, markets.bet9ja_outcome_3_odds),
                scraped_at = excluded.scraped_at
        """, (
            sportradar_id, market_name, specifier or "",
            sporty_market_id, s_o1_name, s_o1_odds, s_o2_name, s_o2_odds, s_o3_name, s_o3_odds,
            pawa_market_id, p_o1_name, p_o1_odds, p_o2_name, p_o2_odds, p_o3_name, p_o3_odds,
            bet9ja_market_id, b_o1_name, b_o1_odds, b_o2_name, b_o2_odds, b_o3_name, b_o3_odds,
            now
        ))
        
        self.conn.commit()
    
    def get_markets_for_event(self, sportradar_id: str) -> list[dict]:
        """Get all markets for a specific event."""
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT * FROM markets 
            WHERE sportradar_id = ?
            ORDER BY market_name, specifier
        """, (sportradar_id,))
        return [dict(row) for row in cursor.fetchall()]
    
    def get_markets_by_type(self, market_name: str) -> list[dict]:
        """Get all markets of a specific type."""
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT m.*, e.home_team, e.away_team, e.start_time
            FROM markets m
            JOIN events e ON m.sportradar_id = e.sportradar_id
            WHERE m.market_name = ?
            ORDER BY e.start_time, m.specifier
        """, (market_name,))
        return [dict(row) for row in cursor.fetchall()]
    
    def get_matched_markets(self) -> list[dict]:
        """Get markets that have odds from both bookmakers."""
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT m.*, e.home_team, e.away_team, e.start_time
            FROM markets m
            JOIN events e ON m.sportradar_id = e.sportradar_id
            WHERE m.sporty_outcome_1_odds IS NOT NULL 
              AND m.pawa_outcome_1_odds IS NOT NULL
            ORDER BY e.start_time, m.market_name
        """)
        return [dict(row) for row in cursor.fetchall()]
    
    # ==========================================
    # Market Snapshot Operations (Historical)
    # ==========================================
    
    def upsert_market_snapshot(
        self,
        scraping_history_id: int,
        sportradar_id: str,
        market_name: str,
        specifier: str = "",
        sporty_market_id: str = None,
        sporty_outcomes: list = None,
        pawa_market_id: str = None,
        pawa_outcomes: list = None,
        bet9ja_market_id: str = None,
        bet9ja_outcomes: list = None,
    ) -> int:
        """
        Insert or update a market snapshot for historical tracking.
        Mirrors the markets table structure with both bookmakers in one row.
        
        Args:
            scraping_history_id: ID of the match scraping session
            sportradar_id: Event ID
            market_name: Unified market name
            specifier: Market specifier (e.g., "2.5" for O/U)
            sporty_market_id: Sportybet market ID
            sporty_outcomes: List of outcome dicts with desc and odds
            pawa_market_id: Betpawa market ID
            pawa_outcomes: List of outcome dicts with name and odds
            
        Returns:
            ID of the snapshot
        """
        cursor = self.conn.cursor()
        
        # Parse Sportybet outcomes
        s1_name, s1_odds = None, None
        s2_name, s2_odds = None, None
        s3_name, s3_odds = None, None
        
        if sporty_outcomes:
            if len(sporty_outcomes) > 0:
                s1_name = sporty_outcomes[0].get("desc")
                s1_odds = float(sporty_outcomes[0].get("odds", 0)) if sporty_outcomes[0].get("odds") else None
            if len(sporty_outcomes) > 1:
                s2_name = sporty_outcomes[1].get("desc")
                s2_odds = float(sporty_outcomes[1].get("odds", 0)) if sporty_outcomes[1].get("odds") else None
            if len(sporty_outcomes) > 2:
                s3_name = sporty_outcomes[2].get("desc")
                s3_odds = float(sporty_outcomes[2].get("odds", 0)) if sporty_outcomes[2].get("odds") else None
        
        # Parse Betpawa outcomes
        p1_name, p1_odds = None, None
        p2_name, p2_odds = None, None
        p3_name, p3_odds = None, None
        
        if pawa_outcomes:
            if len(pawa_outcomes) > 0:
                p1_name = pawa_outcomes[0].get("name")
                p1_odds = float(pawa_outcomes[0].get("odds", 0)) if pawa_outcomes[0].get("odds") else None
            if len(pawa_outcomes) > 1:
                p2_name = pawa_outcomes[1].get("name")
                p2_odds = float(pawa_outcomes[1].get("odds", 0)) if pawa_outcomes[1].get("odds") else None
            if len(pawa_outcomes) > 2:
                p3_name = pawa_outcomes[2].get("name")
                p3_odds = float(pawa_outcomes[2].get("odds", 0)) if pawa_outcomes[2].get("odds") else None

        # Parse Bet9ja outcomes
        b1_name, b1_odds = None, None
        b2_name, b2_odds = None, None
        b3_name, b3_odds = None, None

        if bet9ja_outcomes:
            if len(bet9ja_outcomes) > 0:
                b1_name = bet9ja_outcomes[0].get("desc") or bet9ja_outcomes[0].get("name")
                try:
                    b1_odds = float(bet9ja_outcomes[0].get("odds", 0)) if bet9ja_outcomes[0].get("odds") else None
                except Exception:
                    b1_odds = None
            if len(bet9ja_outcomes) > 1:
                b2_name = bet9ja_outcomes[1].get("desc") or bet9ja_outcomes[1].get("name")
                try:
                    b2_odds = float(bet9ja_outcomes[1].get("odds", 0)) if bet9ja_outcomes[1].get("odds") else None
                except Exception:
                    b2_odds = None
            if len(bet9ja_outcomes) > 2:
                b3_name = bet9ja_outcomes[2].get("desc") or bet9ja_outcomes[2].get("name")
                try:
                    b3_odds = float(bet9ja_outcomes[2].get("odds", 0)) if bet9ja_outcomes[2].get("odds") else None
                except Exception:
                    b3_odds = None
        
        # Use INSERT OR REPLACE to handle upserts
        cursor.execute("""
            INSERT INTO market_snapshots (
                scraping_history_id, sportradar_id, market_name, specifier,
                sporty_market_id, sporty_outcome_1_name, sporty_outcome_1_odds,
                sporty_outcome_2_name, sporty_outcome_2_odds, sporty_outcome_3_name, sporty_outcome_3_odds,
                pawa_market_id, pawa_outcome_1_name, pawa_outcome_1_odds,
                pawa_outcome_2_name, pawa_outcome_2_odds, pawa_outcome_3_name, pawa_outcome_3_odds,
                bet9ja_market_id, bet9ja_outcome_1_name, bet9ja_outcome_1_odds,
                bet9ja_outcome_2_name, bet9ja_outcome_2_odds, bet9ja_outcome_3_name, bet9ja_outcome_3_odds
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(scraping_history_id, sportradar_id, market_name, specifier) DO UPDATE SET
                sporty_market_id = COALESCE(excluded.sporty_market_id, sporty_market_id),
                sporty_outcome_1_name = COALESCE(excluded.sporty_outcome_1_name, sporty_outcome_1_name),
                sporty_outcome_1_odds = COALESCE(excluded.sporty_outcome_1_odds, sporty_outcome_1_odds),
                sporty_outcome_2_name = COALESCE(excluded.sporty_outcome_2_name, sporty_outcome_2_name),
                sporty_outcome_2_odds = COALESCE(excluded.sporty_outcome_2_odds, sporty_outcome_2_odds),
                sporty_outcome_3_name = COALESCE(excluded.sporty_outcome_3_name, sporty_outcome_3_name),
                sporty_outcome_3_odds = COALESCE(excluded.sporty_outcome_3_odds, sporty_outcome_3_odds),
                pawa_market_id = COALESCE(excluded.pawa_market_id, pawa_market_id),
                pawa_outcome_1_name = COALESCE(excluded.pawa_outcome_1_name, pawa_outcome_1_name),
                pawa_outcome_1_odds = COALESCE(excluded.pawa_outcome_1_odds, pawa_outcome_1_odds),
                pawa_outcome_2_name = COALESCE(excluded.pawa_outcome_2_name, pawa_outcome_2_name),
                pawa_outcome_2_odds = COALESCE(excluded.pawa_outcome_2_odds, pawa_outcome_2_odds),
                pawa_outcome_3_name = COALESCE(excluded.pawa_outcome_3_name, pawa_outcome_3_name),
                pawa_outcome_3_odds = COALESCE(excluded.pawa_outcome_3_odds, pawa_outcome_3_odds),
                bet9ja_market_id = COALESCE(excluded.bet9ja_market_id, bet9ja_market_id),
                bet9ja_outcome_1_name = COALESCE(excluded.bet9ja_outcome_1_name, bet9ja_outcome_1_name),
                bet9ja_outcome_1_odds = COALESCE(excluded.bet9ja_outcome_1_odds, bet9ja_outcome_1_odds),
                bet9ja_outcome_2_name = COALESCE(excluded.bet9ja_outcome_2_name, bet9ja_outcome_2_name),
                bet9ja_outcome_2_odds = COALESCE(excluded.bet9ja_outcome_2_odds, bet9ja_outcome_2_odds),
                bet9ja_outcome_3_name = COALESCE(excluded.bet9ja_outcome_3_name, bet9ja_outcome_3_name),
                bet9ja_outcome_3_odds = COALESCE(excluded.bet9ja_outcome_3_odds, bet9ja_outcome_3_odds)
        """, (
            scraping_history_id, sportradar_id, market_name, specifier or "",
            sporty_market_id, s1_name, s1_odds, s2_name, s2_odds, s3_name, s3_odds,
            pawa_market_id, p1_name, p1_odds, p2_name, p2_odds, p3_name, p3_odds,
            bet9ja_market_id, b1_name, b1_odds, b2_name, b2_odds, b3_name, b3_odds
        ))
        
        self.conn.commit()
        return cursor.lastrowid
    
    def get_snapshots_for_session(self, scraping_history_id: int) -> list[dict]:
        """Get all market snapshots for a match session."""
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT ms.*, e.home_team, e.away_team
            FROM market_snapshots ms
            JOIN events e ON ms.sportradar_id = e.sportradar_id
            WHERE ms.scraping_history_id = ?
            ORDER BY ms.market_name, ms.specifier
        """, (scraping_history_id,))
        return [dict(row) for row in cursor.fetchall()]
    
    def get_snapshots_for_event(self, sportradar_id: str, scraping_history_id: int = None) -> list[dict]:
        """
        Get market snapshots for an event.
        
        Args:
            sportradar_id: Event ID
            scraping_history_id: If provided, get specific snapshot; otherwise get latest
            
        Returns:
            List of snapshot dicts
        """
        cursor = self.conn.cursor()
        
        if scraping_history_id:
            cursor.execute("""
                SELECT * FROM market_snapshots 
                WHERE sportradar_id = ? AND scraping_history_id = ?
                ORDER BY market_name, specifier
            """, (sportradar_id, scraping_history_id))
        else:
            # Get latest snapshots (from most recent scraping session)
            cursor.execute("""
                SELECT ms.* FROM market_snapshots ms
                JOIN (
                    SELECT MAX(scraping_history_id) as max_id
                    FROM market_snapshots
                    WHERE sportradar_id = ?
                ) latest ON ms.scraping_history_id = latest.max_id
                WHERE ms.sportradar_id = ?
                ORDER BY ms.market_name, ms.specifier
            """, (sportradar_id, sportradar_id))
        
        return [dict(row) for row in cursor.fetchall()]
    
    def create_snapshot_for_event(self, sportradar_id: str, tournament_id: str = None) -> int:
        """
        Create a snapshot of current markets for an event.
        
        This creates a new scraping session and copies all current markets
        from the markets table to market_snapshots.
        
        Args:
            sportradar_id: The event/match ID
            tournament_id: Optional tournament ID for reference
            
        Returns:
            The scraping_history session ID
        """
        cursor = self.conn.cursor()
        
        # Create a new session for this match
        session_id = self.start_match_session(sportradar_id, tournament_id)
        
        # Copy current markets to snapshots
        cursor.execute("""
            INSERT INTO market_snapshots (
                scraping_history_id, sportradar_id, market_name, specifier,
                sporty_market_id, sporty_outcome_1_name, sporty_outcome_1_odds,
                sporty_outcome_2_name, sporty_outcome_2_odds, sporty_outcome_3_name, sporty_outcome_3_odds,
                pawa_market_id, pawa_outcome_1_name, pawa_outcome_1_odds,
                pawa_outcome_2_name, pawa_outcome_2_odds, pawa_outcome_3_name, pawa_outcome_3_odds,
                bet9ja_market_id, bet9ja_outcome_1_name, bet9ja_outcome_1_odds,
                bet9ja_outcome_2_name, bet9ja_outcome_2_odds, bet9ja_outcome_3_name, bet9ja_outcome_3_odds
            )
            SELECT 
                ?, sportradar_id, market_name, specifier,
                sporty_market_id, sporty_outcome_1_name, sporty_outcome_1_odds,
                sporty_outcome_2_name, sporty_outcome_2_odds, sporty_outcome_3_name, sporty_outcome_3_odds,
                pawa_market_id, pawa_outcome_1_name, pawa_outcome_1_odds,
                pawa_outcome_2_name, pawa_outcome_2_odds, pawa_outcome_3_name, pawa_outcome_3_odds,
                bet9ja_market_id, bet9ja_outcome_1_name, bet9ja_outcome_1_odds,
                bet9ja_outcome_2_name, bet9ja_outcome_2_odds, bet9ja_outcome_3_name, bet9ja_outcome_3_odds
            FROM markets
            WHERE sportradar_id = ?
        """, (session_id, sportradar_id))
        
        self.conn.commit()
        return session_id
    
    def create_snapshots_for_matched_events(self, tournament_id: str = None) -> list[int]:
        """
        Create snapshots for all matched events (events with both bookmaker odds).
        
        Args:
            tournament_id: If provided, only create snapshots for this tournament
            
        Returns:
            List of session IDs created
        """
        cursor = self.conn.cursor()
        
        # Get matched events
        if tournament_id:
            cursor.execute("""
                SELECT DISTINCT e.sportradar_id
                FROM events e
                JOIN markets m ON e.sportradar_id = m.sportradar_id
                WHERE e.matched = 1
                AND m.sporty_outcome_1_odds IS NOT NULL
                AND m.pawa_outcome_1_odds IS NOT NULL
                AND e.sporty_tournament_id = ?
            """, (tournament_id,))
        else:
            cursor.execute("""
                SELECT DISTINCT e.sportradar_id
                FROM events e
                JOIN markets m ON e.sportradar_id = m.sportradar_id
                WHERE e.matched = 1
                AND m.sporty_outcome_1_odds IS NOT NULL
                AND m.pawa_outcome_1_odds IS NOT NULL
            """)
        
        session_ids = []
        for row in cursor.fetchall():
            sportradar_id = row[0]
            session_id = self.create_snapshot_for_event(sportradar_id, tournament_id)
            session_ids.append(session_id)
        
        return session_ids
    
    def get_unprocessed_sessions(self) -> list[dict]:
        """Get match sessions that haven't had engines run on them yet."""
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT sh.*, e.home_team, e.away_team, e.tournament_name
            FROM scraping_history sh
            JOIN events e ON sh.sportradar_id = e.sportradar_id
            WHERE sh.status = 'completed'
            AND NOT EXISTS (
                SELECT 1 FROM engine_calculations ec
                WHERE ec.scraping_history_id = sh.id
            )
            ORDER BY sh.scraped_at
        """)
        return [dict(row) for row in cursor.fetchall()]
    
    def get_stats(self) -> dict:
        """Get database statistics."""
        cursor = self.conn.cursor()
        
        cursor.execute("SELECT COUNT(*) FROM events")
        total_events = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM events WHERE matched = 1")
        matched_events = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM markets")
        total_markets = cursor.fetchone()[0]
        
        cursor.execute("""
            SELECT COUNT(*) FROM markets 
            WHERE sporty_outcome_1_odds IS NOT NULL 
              AND pawa_outcome_1_odds IS NOT NULL
        """)
        matched_markets = cursor.fetchone()[0]
        
        cursor.execute("""
            SELECT market_name, COUNT(*) as cnt 
            FROM markets GROUP BY market_name ORDER BY cnt DESC
        """)
        markets_by_type = {row[0]: row[1] for row in cursor.fetchall()}
        
        # Scraping history stats (now match-based sessions)
        cursor.execute("SELECT COUNT(*) FROM scraping_history WHERE status = 'completed'")
        total_sessions = cursor.fetchone()[0]
        
        # Snapshot stats
        cursor.execute("SELECT COUNT(*) FROM market_snapshots")
        total_snapshots = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM tournaments")
        total_tournaments = cursor.fetchone()[0]
        
        return {
            "total_events": total_events,
            "matched_events": matched_events,
            "total_markets": total_markets,
            "matched_markets": matched_markets,
            "markets_by_type": markets_by_type,
            "total_sessions": total_sessions,
            "total_snapshots": total_snapshots,
            "total_tournaments": total_tournaments,
        }
    
    def get_1x2_odds(self, sportradar_id: str, bookmaker: str = None) -> dict:
        """
        Get cached 1X2 odds for an event.
        
        Args:
            sportradar_id: Event ID
            bookmaker: 'sporty', 'pawa', or None for both
            
        Returns:
            Dict with odds: {sporty: {home, draw, away}, pawa: {home, draw, away}}
        """
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT sporty_1x2_home, sporty_1x2_draw, sporty_1x2_away,
                   pawa_1x2_home, pawa_1x2_draw, pawa_1x2_away
            FROM events WHERE sportradar_id = ?
        """, (sportradar_id,))
        
        row = cursor.fetchone()
        if not row:
            return {}
        
        result = {
            "sporty": {
                "home": row[0],
                "draw": row[1],
                "away": row[2],
            },
            "pawa": {
                "home": row[3],
                "draw": row[4],
                "away": row[5],
            }
        }
        
        if bookmaker:
            return result.get(bookmaker, {})
        return result
    
    def clear_all(self):
        """Clear all data from database."""
        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM engine_calculations")
        cursor.execute("DELETE FROM market_snapshots")
        cursor.execute("DELETE FROM markets")
        cursor.execute("DELETE FROM scraping_history")
        cursor.execute("DELETE FROM events")
        self.conn.commit()
        logger.warning("All data cleared from database")

    def clear_bet9ja_columns_for_event(self, sportradar_id: str):
        """Clear Bet9ja-specific columns for a given event to remove stale data."""
        cursor = self.conn.cursor()
        cursor.execute("""
            UPDATE markets SET
                bet9ja_market_id = NULL,
                bet9ja_outcome_1_name = NULL,
                bet9ja_outcome_1_odds = NULL,
                bet9ja_outcome_2_name = NULL,
                bet9ja_outcome_2_odds = NULL,
                bet9ja_outcome_3_name = NULL,
                bet9ja_outcome_3_odds = NULL
            WHERE sportradar_id = ?
        """, (sportradar_id,))
        cursor.execute("DELETE FROM market_snapshots WHERE sportradar_id = ?", (sportradar_id,))
        self.conn.commit()
    
    # ==========================================
    # Engine Calculation Operations
    # ==========================================
    
    def insert_engine_calculation(
        self,
        sportradar_id: str,
        engine_name: str,
        bookmaker: str,
        lambda_home: float,
        lambda_away: float,
        lambda_total: float,
        p_home_1up: float,
        p_away_1up: float,
        fair_home: float,
        fair_away: float,
        fair_draw: float,
        scraping_history_id: int = None,
        # Backwards-compatible Sportybet actuals (keeps original column)
        actual_home: float = None,
        actual_away: float = None,
        actual_draw: float = None,
        # Explicit per-source actual 1UP odds
        actual_sporty_home: float = None,
        actual_sporty_draw: float = None,
        actual_sporty_away: float = None,
        actual_bet9ja_home: float = None,
        actual_bet9ja_draw: float = None,
        actual_bet9ja_away: float = None,
    ) -> int:
        """
        Insert an engine calculation result.
        
        Args:
            sportradar_id: Event ID
            engine_name: Name of the engine (e.g., 'Poisson', 'FirstGoal')
            bookmaker: Source of input odds ('sporty' or 'pawa')
            lambda_home: Inferred home team expected goals
            lambda_away: Inferred away team expected goals
            lambda_total: Total expected goals
            p_home_1up: Probability of home 1UP payout
            p_away_1up: Probability of away 1UP payout
            fair_home: Fair odds for home 1UP
            fair_away: Fair odds for away 1UP
            fair_draw: Draw odds (unchanged from 1X2)
            scraping_history_id: Links to specific market snapshot
            actual_home: Sportybet actual home 1UP odds
            actual_away: Sportybet actual away 1UP odds
            actual_draw: Sportybet actual draw 1UP odds
            
        Returns:
            ID of inserted calculation
        """
        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO engine_calculations (
                sportradar_id, scraping_history_id, engine_name, bookmaker,
                lambda_home, lambda_away, lambda_total,
                p_home_1up, p_away_1up,
                fair_home, fair_away, fair_draw,
                actual_home, actual_away, actual_draw,
                actual_sporty_home, actual_sporty_draw, actual_sporty_away,
                actual_bet9ja_home, actual_bet9ja_draw, actual_bet9ja_away,
                calculated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        """, (
            sportradar_id, scraping_history_id, engine_name, bookmaker,
            lambda_home, lambda_away, lambda_total,
            p_home_1up, p_away_1up,
            fair_home, fair_away, fair_draw,
            actual_home, actual_away, actual_draw,
            actual_sporty_home, actual_sporty_draw, actual_sporty_away,
            actual_bet9ja_home, actual_bet9ja_draw, actual_bet9ja_away,
        ))
        self.conn.commit()
        return cursor.lastrowid
    
    # Keep for backwards compatibility
    def upsert_engine_calculation(self, **kwargs):
        """Legacy method - now just inserts (for backwards compat)."""
        return self.insert_engine_calculation(**kwargs)
    
    def get_engine_calculations(self, sportradar_id: str = None, engine_name: str = None) -> list[dict]:
        """
        Get engine calculation results.
        
        Args:
            sportradar_id: Filter by event ID (optional)
            engine_name: Filter by engine name (optional)
            
        Returns:
            List of calculation result dicts
        """
        cursor = self.conn.cursor()
        
        query = "SELECT * FROM engine_calculations WHERE 1=1"
        params = []
        
        if sportradar_id:
            query += " AND sportradar_id = ?"
            params.append(sportradar_id)
        
        if engine_name:
            query += " AND engine_name = ?"
            params.append(engine_name)
        
        query += " ORDER BY sportradar_id, engine_name, bookmaker"
        
        cursor.execute(query, params)
        return [dict(row) for row in cursor.fetchall()]
    
    def get_engine_accuracy_stats(self, margin: float = 0.06) -> list[dict]:
        """
        Calculate accuracy statistics for each engine at a given margin.
        
        Args:
            margin: Margin to apply to fair odds for comparison
            
        Returns:
            List of stats per engine/bookmaker
        """
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT 
                engine_name,
                bookmaker,
                COUNT(*) as n_events,
                AVG(ABS(fair_home * (1 - ?) - actual_home)) as mae_home,
                AVG(ABS(fair_away * (1 - ?) - actual_away)) as mae_away,
                AVG((ABS(fair_home * (1 - ?) - actual_home) + ABS(fair_away * (1 - ?) - actual_away)) / 2) as mae_total
            FROM engine_calculations
            WHERE actual_home IS NOT NULL
            GROUP BY engine_name, bookmaker
            ORDER BY mae_total ASC
        """, (margin, margin, margin, margin))
        
        return [dict(row) for row in cursor.fetchall()]
