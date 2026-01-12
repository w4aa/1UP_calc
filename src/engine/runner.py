"""
Engine Runner Service

Runs all 1UP pricing engines on events and stores results in database.
This module integrates with the main scraper workflow.

Uses ThreadPoolExecutor for parallel event calculations.
"""

import logging
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional

from src.db.manager import DatabaseManager
from src.config import ConfigLoader
from src.engine import CalibratedPoissonEngine, FTSCalibratedDPEngine

logger = logging.getLogger(__name__)

# Number of parallel workers (default: CPU count, min 2)
DEFAULT_WORKERS = max(2, os.cpu_count() or 4)


class EngineRunner:
    """
    Runs all 1UP pricing engines on scraped events.

    Usage:
        runner = EngineRunner(db)
        runner.run_all_events()  # Process all matched events
        runner.run_event(sportradar_id)  # Process single event
    """

    def __init__(self, db: DatabaseManager, config: ConfigLoader = None):
        """
        Initialize engine runner.

        Args:
            db: Database manager instance (must be connected)
            config: Config loader (optional, will create if not provided)
        """
        self.db = db
        self.config = config or ConfigLoader()

        # Load simulation settings
        sim_config = self.config.get_engine_simulation_settings()

        # Initialize engines with no margin (compute fair odds)
        engine_params = {
            'n_sims': sim_config['n_sims'],
            'match_minutes': sim_config['match_minutes'],
            'margin_pct': 0.0,  # Fair odds - no margin
        }

        # Initialize both engines for comparison
        self.engines = [
            CalibratedPoissonEngine(**engine_params),
            FTSCalibratedDPEngine(**engine_params),
        ]

        logger.info(f"EngineRunner initialized with {len(self.engines)} engine(s)")
        for engine in self.engines:
            logger.info(f"  - {engine.name}")
        logger.info(f"  Simulations: {sim_config['n_sims']:,}")
    
    def _compute_event(self, markets_raw: list, sportradar_id: str, scraping_history_id: int = None) -> list:
        """
        Compute engine results for a single event (no DB operations).

        Calculates 1UP odds using market data from all 3 bookmakers (sporty, pawa, bet9ja).
        Stores appropriate actual 1UP odds based on bookmaker source.

        Args:
            markets_raw: Market data for the event
            sportradar_id: Event ID
            scraping_history_id: Scraping session ID (for duplicate checking)

        Returns:
            List of calculation result dicts ready for DB insertion
        """
        # Check if calculations already exist for this snapshot
        if scraping_history_id:
            existing = self.db.get_calculation_for_snapshot(sportradar_id, scraping_history_id)
            if existing:
                logger.debug(f"Skipping {sportradar_id} - calculations already exist for history_id {scraping_history_id}")
                return []

        if not markets_raw:
            return []

        # Prepare market data for all 3 bookmakers
        sporty_data = self._prepare_market_data(markets_raw, 'sporty')
        pawa_data = self._prepare_market_data(markets_raw, 'pawa')
        bet9ja_data = self._prepare_market_data(markets_raw, 'bet9ja')

        # Get actual 1UP odds from both Sportybet and Bet9ja
        actual_1up = self._get_1up_actual_odds(markets_raw)

        results = []

        for engine in self.engines:
            for bookmaker, data in [('sporty', sporty_data), ('pawa', pawa_data), ('bet9ja', bet9ja_data)]:
                result = engine.calculate(data, bookmaker)

                if result:
                    # Always attach both Sportybet and Bet9ja actual 1UP odds
                    sporty_actual = actual_1up.get('sporty', (None, None, None))
                    bet9ja_actual = actual_1up.get('bet9ja', (None, None, None))

                    results.append({
                        'sportradar_id': sportradar_id,
                        'engine_name': result['engine'],
                        'bookmaker': bookmaker,
                        'lambda_home': result['lambda_home'],
                        'lambda_away': result['lambda_away'],
                        'lambda_total': result['lambda_total'],
                        'p_home_1up': result['p_home_1up'],
                        'p_away_1up': result['p_away_1up'],
                        'fair_home': result['1up_home_fair'],
                        'fair_away': result['1up_away_fair'],
                        'fair_draw': result['1up_draw'],
                        'actual_sporty_home': sporty_actual[0],
                        'actual_sporty_draw': sporty_actual[1],
                        'actual_sporty_away': sporty_actual[2],
                        'actual_bet9ja_home': bet9ja_actual[0],
                        'actual_bet9ja_draw': bet9ja_actual[1],
                        'actual_bet9ja_away': bet9ja_actual[2],
                    })

        return results
    
    def run_event(self, sportradar_id: str, scraping_history_id: int = None) -> int:
        """
        Run all engines on a single event.
        
        Args:
            sportradar_id: Event ID to process
            scraping_history_id: Link calculations to this scraping session
            
        Returns:
            Number of calculations stored
        """
        # Get markets for this event
        markets_raw = self.db.get_markets_for_event(sportradar_id)

        if not markets_raw:
            logger.debug(f"No markets found for event {sportradar_id}")
            return 0

        # Compute results
        results = self._compute_event(markets_raw, sportradar_id, scraping_history_id)
        
        # Store to DB
        for calc in results:
            self.db.insert_engine_calculation(
                sportradar_id=calc['sportradar_id'],
                scraping_history_id=scraping_history_id,
                engine_name=calc['engine_name'],
                bookmaker=calc['bookmaker'],
                lambda_home=calc['lambda_home'],
                lambda_away=calc['lambda_away'],
                lambda_total=calc['lambda_total'],
                p_home_1up=calc['p_home_1up'],
                p_away_1up=calc['p_away_1up'],
                fair_home=calc['fair_home'],
                fair_away=calc['fair_away'],
                fair_draw=calc['fair_draw'],
                actual_sporty_home=calc.get('actual_sporty_home'),
                actual_sporty_draw=calc.get('actual_sporty_draw'),
                actual_sporty_away=calc.get('actual_sporty_away'),
                actual_bet9ja_home=calc.get('actual_bet9ja_home'),
                actual_bet9ja_draw=calc.get('actual_bet9ja_draw'),
                actual_bet9ja_away=calc.get('actual_bet9ja_away'),
            )
        
        return len(results)
    
    def run_all_events(self, tournament_id: str = None, parallel: bool = True, max_workers: int = None) -> dict:
        """
        Run all engines on all matched events.
        
        Args:
            tournament_id: Optional filter by tournament
            parallel: Use parallel processing (default True)
            max_workers: Number of parallel workers (default: CPU count)
            
        Returns:
            Summary dict with counts
        """
        cursor = self.db.conn.cursor()
        
        if tournament_id:
            cursor.execute("""
                SELECT sportradar_id, home_team, away_team 
                FROM events 
                WHERE matched = 1 AND sporty_tournament_id = ?
            """, (tournament_id,))
        else:
            cursor.execute("""
                SELECT sportradar_id, home_team, away_team 
                FROM events 
                WHERE matched = 1
            """)
        
        events = cursor.fetchall()
        
        if not events:
            logger.info("No matched events found to process")
            return {'events': 0, 'calculations': 0}
        
        workers = max_workers or DEFAULT_WORKERS
        logger.info(f"Running engines on {len(events)} events (parallel={parallel}, workers={workers})...")
        
        if parallel and len(events) > 1:
            return self._run_events_parallel(events, workers)
        else:
            return self._run_events_sequential(events)
    
    def _run_events_sequential(self, events: list) -> dict:
        """Run events sequentially (original behavior)."""
        total_calculations = 0
        events_processed = 0
        
        for i, row in enumerate(events):
            sportradar_id = row['sportradar_id']
            print(f"  [{i+1}/{len(events)}] {row['home_team']} vs {row['away_team']}...", end=" ", flush=True)
            
            # Get latest scraping session for this event
            latest_session = self.db.get_latest_match_session(sportradar_id)
            session_id = latest_session['id'] if latest_session else None
            
            calcs = self.run_event(sportradar_id, scraping_history_id=session_id)
            
            if calcs > 0:
                events_processed += 1
                total_calculations += calcs
                print(f"{calcs} calcs")
            else:
                print("skipped")
        
        logger.info(f"Engine calculations complete: {events_processed} events, {total_calculations} calculations")
        
        return {
            'events': events_processed,
            'calculations': total_calculations,
        }
    
    def _run_events_parallel(self, events: list, max_workers: int) -> dict:
        """
        Run events in parallel - fetch markets, compute in threads, store results.
        
        SQLite is read from main thread, computation is parallel, writes are main thread.
        """
        total = len(events)
        
        # Step 1: Pre-fetch all market data from DB (main thread)
        print(f"  Loading market data for {total} events...", flush=True)
        event_data = []
        for row in events:
            sportradar_id = row['sportradar_id']
            markets_raw = self.db.get_markets_for_event(sportradar_id)
            
            # Get latest scraping session for this event
            latest_session = self.db.get_latest_match_session(sportradar_id)
            session_id = latest_session['id'] if latest_session else None
            
            event_data.append({
                'sportradar_id': sportradar_id,
                'home_team': row['home_team'],
                'away_team': row['away_team'],
                'markets': markets_raw,
                'scraping_history_id': session_id,
            })
        
        # Step 2: Parallel computation (no DB access)
        print(f"  Computing {total} events with {max_workers} workers...", flush=True)
        all_results = []
        
        def compute_one(data):
            results = self._compute_event(data['markets'], data['sportradar_id'], data['scraping_history_id'])
            return {
                'sportradar_id': data['sportradar_id'],
                'home_team': data['home_team'],
                'away_team': data['away_team'],
                'calculations': results,
                'scraping_history_id': data['scraping_history_id'],
            }
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(compute_one, d): d for d in event_data}
            completed = 0
            
            for future in as_completed(futures):
                completed += 1
                result = future.result()
                all_results.append(result)
                n_calcs = len(result['calculations'])
                status = f"{n_calcs} calcs" if n_calcs > 0 else "skipped"
                print(f"  [{completed}/{total}] {result['home_team']} vs {result['away_team']}... {status}")
        
        # Step 3: Store all results to DB (main thread)
        total_calculations = 0
        events_processed = 0
        
        for result in all_results:
            calcs = result['calculations']
            if calcs:
                events_processed += 1
                total_calculations += len(calcs)
                for calc in calcs:
                    self.db.insert_engine_calculation(
                        sportradar_id=calc['sportradar_id'],
                        scraping_history_id=result['scraping_history_id'],
                        engine_name=calc['engine_name'],
                        bookmaker=calc['bookmaker'],
                        lambda_home=calc['lambda_home'],
                        lambda_away=calc['lambda_away'],
                        lambda_total=calc['lambda_total'],
                        p_home_1up=calc['p_home_1up'],
                        p_away_1up=calc['p_away_1up'],
                        fair_home=calc['fair_home'],
                        fair_away=calc['fair_away'],
                        fair_draw=calc['fair_draw'],
                        actual_sporty_home=calc.get('actual_sporty_home'),
                        actual_sporty_draw=calc.get('actual_sporty_draw'),
                        actual_sporty_away=calc.get('actual_sporty_away'),
                        actual_bet9ja_home=calc.get('actual_bet9ja_home'),
                        actual_bet9ja_draw=calc.get('actual_bet9ja_draw'),
                        actual_bet9ja_away=calc.get('actual_bet9ja_away'),
                    )
        
        logger.info(f"Engine calculations complete: {events_processed} events, {total_calculations} calculations")
        
        return {
            'events': events_processed,
            'calculations': total_calculations,
        }
    
    def run_new_snapshots(self, parallel: bool = True, max_workers: int = None) -> dict:
        """
        Run engines on match sessions that haven't been processed yet.
        
        This ensures we calculate on each new snapshot of odds separately,
        building historical tracking of how calculated odds change.
        
        Args:
            parallel: Use parallel processing (default True)
            max_workers: Number of parallel workers (default: CPU count)
        
        Returns:
            Summary dict with counts
        """
        # Get unprocessed match sessions
        sessions = self.db.get_unprocessed_sessions()
        
        if not sessions:
            logger.info("No new match sessions to process")
            return {'sessions': 0, 'events': 0, 'calculations': 0}
        
        workers = max_workers or DEFAULT_WORKERS
        logger.info(f"Processing {len(sessions)} new match sessions (parallel={parallel}, workers={workers})...")
        
        if parallel and len(sessions) > 1:
            return self._run_sessions_parallel(sessions, workers)
        else:
            return self._run_sessions_sequential(sessions)
    
    def _run_sessions_sequential(self, sessions: list) -> dict:
        """Run sessions sequentially."""
        total_events = 0
        total_calculations = 0
        
        for session in sessions:
            session_id = session['id']
            sportradar_id = session['sportradar_id']
            home_team = session.get('home_team', 'Unknown')
            away_team = session.get('away_team', 'Unknown')
            
            print(f"  Session {session_id}: {home_team} vs {away_team}...", end=" ", flush=True)
            
            calcs = self.run_event(sportradar_id, scraping_history_id=session_id)
            if calcs > 0:
                total_events += 1
                total_calculations += calcs
                print(f"{calcs} calcs")
            else:
                print("skipped")
        
        logger.info(f"\nSnapshot processing complete: {len(sessions)} sessions, {total_events} events, {total_calculations} calculations")
        
        return {
            'sessions': len(sessions),
            'events': total_events,
            'calculations': total_calculations,
        }
    
    def _run_sessions_parallel(self, sessions: list, max_workers: int) -> dict:
        """
        Run sessions in parallel - fetch markets, compute in threads, store results.
        
        SQLite is read from main thread, computation is parallel, writes are main thread.
        """
        total = len(sessions)
        
        # Step 1: Pre-fetch all market data from DB (main thread)
        print(f"  Loading market data for {total} sessions...", flush=True)
        session_data = []
        for session in sessions:
            sportradar_id = session['sportradar_id']
            markets_raw = self.db.get_markets_for_event(sportradar_id)
            session_data.append({
                'session_id': session['id'],
                'sportradar_id': sportradar_id,
                'home_team': session.get('home_team', 'Unknown'),
                'away_team': session.get('away_team', 'Unknown'),
                'markets': markets_raw,
            })
        
        # Step 2: Parallel computation (no DB access)
        print(f"  Computing {total} sessions with {max_workers} workers...", flush=True)
        all_results = []
        
        def compute_one(data):
            results = self._compute_event(data['markets'], data['sportradar_id'], data['session_id'])
            return {
                'session_id': data['session_id'],
                'sportradar_id': data['sportradar_id'],
                'home_team': data['home_team'],
                'away_team': data['away_team'],
                'calculations': results,
            }
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(compute_one, d): d for d in session_data}
            completed = 0
            
            for future in as_completed(futures):
                completed += 1
                result = future.result()
                all_results.append(result)
                n_calcs = len(result['calculations'])
                status = f"{n_calcs} calcs" if n_calcs > 0 else "skipped"
                print(f"  [{completed}/{total}] {result['home_team']} vs {result['away_team']}... {status}")
        
        # Step 3: Store all results to DB (main thread)
        total_calculations = 0
        events_processed = 0
        
        for result in all_results:
            calcs = result['calculations']
            if calcs:
                events_processed += 1
                total_calculations += len(calcs)
                for calc in calcs:
                    self.db.insert_engine_calculation(
                        sportradar_id=calc['sportradar_id'],
                        scraping_history_id=result['session_id'],
                        engine_name=calc['engine_name'],
                        bookmaker=calc['bookmaker'],
                        lambda_home=calc['lambda_home'],
                        lambda_away=calc['lambda_away'],
                        lambda_total=calc['lambda_total'],
                        p_home_1up=calc['p_home_1up'],
                        p_away_1up=calc['p_away_1up'],
                        fair_home=calc['fair_home'],
                        fair_away=calc['fair_away'],
                        fair_draw=calc['fair_draw'],
                        actual_sporty_home=calc.get('actual_sporty_home'),
                        actual_sporty_draw=calc.get('actual_sporty_draw'),
                        actual_sporty_away=calc.get('actual_sporty_away'),
                        actual_bet9ja_home=calc.get('actual_bet9ja_home'),
                        actual_bet9ja_draw=calc.get('actual_bet9ja_draw'),
                        actual_bet9ja_away=calc.get('actual_bet9ja_away'),
                    )
        
        logger.info(f"Snapshot processing complete: {len(sessions)} sessions, {events_processed} events, {total_calculations} calculations")
        
        return {
            'sessions': len(sessions),
            'events': events_processed,
            'calculations': total_calculations,
        }
    
    def _prepare_market_data(self, markets: list[dict], bookmaker: str) -> dict:
        """Prepare market data dictionary for engines."""
        home_1x2, draw_1x2, away_1x2 = self._get_1x2_odds(markets, bookmaker)
        total_line, total_over, total_under = self._find_ou_market(markets, "Over/Under", bookmaker, 2.5)
        home_line, home_over, home_under = self._find_ou_market(markets, "Home O/U", bookmaker, 0.5)
        away_line, away_over, away_under = self._find_ou_market(markets, "Away O/U", bookmaker, 0.5)
        home_lead1_yes, home_lead1_no = self._get_lead1_odds(markets, 'home')
        away_lead1_yes, away_lead1_no = self._get_lead1_odds(markets, 'away')

        # Get FTS odds from ALL bookmakers (for provider-aware selection)
        fts_all = self._get_first_goal_all_bookmakers(markets)

        btts_yes, btts_no = self._get_btts_odds(markets, bookmaker)
        asian_handicap = self._get_asian_handicap_odds(markets, bookmaker)

        return {
            '1x2': (home_1x2, draw_1x2, away_1x2),
            'total_ou': (total_line, total_over, total_under),
            'home_ou': (home_line, home_over, home_under),
            'away_ou': (away_line, away_over, away_under),
            'home_lead1': (home_lead1_yes, home_lead1_no),
            'away_lead1': (away_lead1_yes, away_lead1_no),
            'first_goal': fts_all,  # Dict with 'sporty' and 'bet9ja' keys
            'btts': (btts_yes, btts_no),
            'asian_handicap': asian_handicap,
        }
    
    def _get_market_odds(self, markets: list[dict], market_name: str, specifier: str = "") -> Optional[dict]:
        """Get market odds from a list of markets for all bookmakers."""
        for m in markets:
            if m['market_name'] == market_name and m['specifier'] == specifier:
                return {
                    'sporty': {
                        'outcome_1': m['sporty_outcome_1_odds'],
                        'outcome_2': m['sporty_outcome_2_odds'],
                        'outcome_3': m['sporty_outcome_3_odds'],
                    },
                    'pawa': {
                        'outcome_1': m['pawa_outcome_1_odds'],
                        'outcome_2': m['pawa_outcome_2_odds'],
                        'outcome_3': m['pawa_outcome_3_odds'],
                    },
                    'bet9ja': {
                        'outcome_1': m.get('bet9ja_outcome_1_odds'),
                        'outcome_2': m.get('bet9ja_outcome_2_odds'),
                        'outcome_3': m.get('bet9ja_outcome_3_odds'),
                    }
                }
        return None
    
    def _get_1x2_odds(self, markets: list[dict], bookmaker: str) -> tuple:
        m = self._get_market_odds(markets, "1X2", "")
        if not m:
            return None, None, None
        odds = m[bookmaker]
        return odds['outcome_1'], odds['outcome_2'], odds['outcome_3']
    
    def _get_1up_actual_odds(self, markets: list[dict]) -> dict:
        """
        Get actual 1UP odds from both Sportybet and Bet9ja.

        Returns:
            Dict with 'sporty' and 'bet9ja' keys, each containing (home, draw, away) tuple
        """
        m = self._get_market_odds(markets, "1X2 - 1UP", "")
        if not m:
            return {
                'sporty': (None, None, None),
                'bet9ja': (None, None, None)
            }

        return {
            'sporty': (m['sporty']['outcome_1'], m['sporty']['outcome_2'], m['sporty']['outcome_3']),
            'bet9ja': (m['bet9ja']['outcome_1'], m['bet9ja']['outcome_2'], m['bet9ja']['outcome_3'])
        }
    
    def _find_ou_market(self, markets: list[dict], market_name: str, bookmaker: str, preferred_line: float) -> tuple:
        candidates = []
        for m in markets:
            if m['market_name'] != market_name:
                continue
            try:
                line = float(m['specifier']) if m['specifier'] else None
            except ValueError:
                continue
            if line is None:
                continue
            
            if bookmaker == 'sporty':
                over_odds = m['sporty_outcome_1_odds']
                under_odds = m['sporty_outcome_2_odds']
            else:
                over_odds = m['pawa_outcome_1_odds']
                under_odds = m['pawa_outcome_2_odds']
            
            if over_odds and under_odds:
                candidates.append((line, over_odds, under_odds))
        
        if not candidates:
            return None, None, None
        
        half_lines = [(l, o, u) for l, o, u in candidates if l % 1 == 0.5]
        if half_lines:
            exact = [(l, o, u) for l, o, u in half_lines if abs(l - preferred_line) < 0.01]
            if exact:
                return exact[0]
            return half_lines[0]
        return candidates[0]
    
    def _get_lead1_odds(self, markets: list[dict], team: str) -> tuple:
        market_name = "Home Team Lead by 1" if team == 'home' else "Away Team Lead by 1"
        m = self._get_market_odds(markets, market_name, "")
        if not m:
            return None, None
        odds = m['sporty']
        return odds['outcome_1'], odds['outcome_2']
    
    def _get_first_goal_odds(self, markets: list[dict], bookmaker: str) -> tuple:
        m = self._get_market_odds(markets, "First Team to Score", "1")
        if not m:
            return None, None, None
        odds = m[bookmaker]
        return odds['outcome_1'], odds['outcome_2'], odds['outcome_3']
    
    def _get_btts_odds(self, markets: list[dict], bookmaker: str) -> tuple:
        m = self._get_market_odds(markets, "BTTS", "")
        if not m:
            return None, None
        odds = m[bookmaker]
        return odds['outcome_1'], odds['outcome_2']
    
    def _get_asian_handicap_odds(self, markets: list[dict], bookmaker: str) -> Optional[dict]:
        result = {}
        for m in markets:
            if m['market_name'] != "Asian Handicap":
                continue
            try:
                line = float(m['specifier']) if m['specifier'] else None
            except ValueError:
                continue
            if line is None:
                continue

            if bookmaker == 'sporty':
                home_odds = m['sporty_outcome_1_odds']
                away_odds = m['sporty_outcome_2_odds']
            else:
                home_odds = m['pawa_outcome_1_odds']
                away_odds = m['pawa_outcome_2_odds']

            if home_odds and away_odds:
                result[line] = (home_odds, away_odds)

        return result if result else None

    def _get_first_goal_all_bookmakers(self, markets: list[dict]) -> dict:
        """
        Get First Team to Score odds from ALL bookmakers.

        Critical for FTS-Calibrated engine which needs provider-aware FTS selection:
        - Betpawa uses Sporty FTS (same odds provider)
        - Bet9ja uses its own FTS

        Returns:
            Dict with 'sporty' and 'bet9ja' keys, each containing (fg_home, fg_nog, fg_away) or None
        """
        m = self._get_market_odds(markets, "First Team to Score", "1")
        if not m:
            return {'sporty': None, 'bet9ja': None}

        sporty_fts = None
        if m['sporty']['outcome_1'] and m['sporty']['outcome_2'] and m['sporty']['outcome_3']:
            sporty_fts = (
                m['sporty']['outcome_1'],  # Home
                m['sporty']['outcome_2'],  # No Goal
                m['sporty']['outcome_3']   # Away
            )

        bet9ja_fts = None
        if m['bet9ja']['outcome_1'] and m['bet9ja']['outcome_2'] and m['bet9ja']['outcome_3']:
            bet9ja_fts = (
                m['bet9ja']['outcome_1'],  # Home
                m['bet9ja']['outcome_2'],  # No Goal
                m['bet9ja']['outcome_3']   # Away
            )

        return {
            'sporty': sporty_fts,
            'bet9ja': bet9ja_fts
        }


def run_engines_on_all_events(db_path: str = None) -> dict:
    """
    Convenience function to run engines on new match snapshots.
    
    This processes all unprocessed scraping sessions, ensuring each
    historical snapshot is linked to its calculations.
    
    Args:
        db_path: Optional database path (uses config default if not provided)
        
    Returns:
        Summary dict with counts
    """
    config = ConfigLoader()
    db = DatabaseManager(db_path or config.get_db_path())
    db.connect()
    
    try:
        runner = EngineRunner(db, config)
        return runner.run_new_snapshots()
    finally:
        db.close()
