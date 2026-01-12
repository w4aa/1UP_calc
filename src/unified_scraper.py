"""
Unified Betting Scraper

Orchestrates scraping from both Sportybet and Betpawa,
matching events by Sportradar ID and storing unified odds in SQLite.

This module is called by main.py - use main.py as the entry point.
"""

import asyncio
import logging
import sys
from pathlib import Path
from typing import Optional

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.config import ConfigLoader
from src.db.manager import DatabaseManager
from src.scraper.sporty import SharedBrowserManager, SportybetEventsScraper, SportybetMarketsScraper
from src.scraper.pawa import BetpawaEventsScraper, BetpawaMarketsScraper
from src.scraper.bet9ja import Bet9jaEventsScraper, Bet9jaMarketsScraper
from src.engine.runner import EngineRunner

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


class UnifiedScraper:
    """
    Orchestrates scraping from both bookmakers and stores data in unified database.
    """

    def __init__(self):
        """Initialize the unified scraper."""
        self.config = ConfigLoader()
        self.db = DatabaseManager(self.config.get_db_path())
        self.market_mapping = self.config.get_market_mapping()
        # Explicit per-Bet9ja mapping registry (populate per-market).
        # Keys should be Bet9ja market_id (preferred) or uppercased market_name.
        # Start with the core markets requested by the user.
        self.bet9ja_market_map = {
            'S_1X2': {'market_name': '1X2', 'use_normalize': True},
            # Explicit 1UP / 2UP mappings: prefer exact key ordering when available
            'S_1X21': {
                'market_name': '1X2 - 1UP',
                'use_normalize': False,
                'key_order': ['11', 'X1', '21'],
            },
            'S_1X22': {
                'market_name': '1X2 - 2UP',
                'use_normalize': False,
                'key_order': ['12', 'X2', '22'],
            },
            'S_GGNG': {'market_name': 'BTTS', 'use_normalize': True},
            # Total goals Over/Under (accept only .0 and .5 lines)
            'S_OU': {'market_name': 'Over/Under', 'use_normalize': True},
            # Asian Over/Under (S_OUA) - treat similarly but skip quarter lines (.25/.75)
            'S_OUA': {'market_name': 'Over/Under', 'use_normalize': True},
            # Home/Away specific totals (map by name if market id not exact)
            'HOME O/U': {'market_name': 'Home O/U', 'use_normalize': True},
            'AWAY O/U': {'market_name': 'Away O/U', 'use_normalize': True},
            # Home/Away combined Over/Under (S_HAOU) -> split into Home O/U and Away O/U
            'S_HAOU': [
                {'market_name': 'Home O/U', 'use_normalize': False, 'key_order': ['OH', 'UH']},
                {'market_name': 'Away O/U', 'use_normalize': False, 'key_order': ['OA', 'UA']},
            ],
            # Asian Handicap mapping
            'S_AH': {'market_name': 'Asian Handicap', 'use_normalize': True},
            # First Team to Score (Sporty `sporty_id: 8`) - explicit mapping
            'S_1STGOAL': {
                'market_name': 'First Team to Score',
                'use_normalize': False,
                'key_order': ['1', '2', 'X'],
                'specifier': '1',
            },
            # Explicitly ignore noisy Bet9ja markets we don't need
            'ANY TEAM LEAD BY 1': {'ignore': True},
            'ANY TEAM LEAD BY 2': {'ignore': True},
            'HOME TEAM LEAD BY 1': {'ignore': True},
            'HOME TEAM LEAD BY 2': {'ignore': True},
            'AWAY TEAM LEAD BY 1': {'ignore': True},
            'AWAY TEAM LEAD BY 2': {'ignore': True},
            '2ND HALF - 1X2 & OVER/UNDER': {'ignore': True},
            'CHANCE MIX +': {'ignore': True},
            'OVER/UNDER ASIAN': {'ignore': True},
        }
        # Accept common market_name variants as alternate keys (no dashes, spaced variants)
        self.bet9ja_market_map.update({
            '1X2 1UP': {'market_name': '1X2 - 1UP', 'use_normalize': True},
            '1X2 2UP': {'market_name': '1X2 - 2UP', 'use_normalize': True},
            '1X2-1UP': {'market_name': '1X2 - 1UP', 'use_normalize': True},
            '1X2-2UP': {'market_name': '1X2 - 2UP', 'use_normalize': True},
        })
        # also accept market name variants
        self.bet9ja_market_map.update({
            'FIRST TEAM TO SCORE': {
                'market_name': 'First Team to Score',
                'use_normalize': False,
                'key_order': ['1','2','X'],
                'specifier': '1',
            },
        })
        
        # Get enabled market IDs
        self.sporty_market_ids = self.config.get_sporty_market_ids()
        self.pawa_market_ids = self.config.get_pawa_market_ids()
        # Allowed unified market names (uppercased) from config/markets.yaml
        self.enabled_market_names = {m.get('name', '').upper() for m in self.config.load_markets()}
        
        # Thread-safe lock for database operations
        self._db_lock = asyncio.Lock()
        
        # Shared browser manager for Sportybet
        self._browser_manager = None

        # Load concurrency settings from config
        concurrency = self.config.get_concurrency_settings()
        self.max_pawa_concurrent = concurrency['pawa']
        self.max_sporty_concurrent = concurrency['sporty']
        self.max_bet9ja_concurrent = concurrency['bet9ja']
        self.max_tournaments_concurrent = concurrency['tournaments']

        logger.info(f"Sporty markets enabled: {len(self.sporty_market_ids)}")
        logger.info(f"Pawa markets enabled: {len(self.pawa_market_ids)}")

    def _normalize_specifier(self, specifier: str, specifier_key: str = None) -> str:
        """
        Normalize specifier to a common format.
        
        Sporty format: "total=2.5" or "hcp=1:0"
        Pawa format: "2.5" (raw value)
        
        This converts to just the value: "2.5"
        """
        if not specifier:
            return ""
        
        # Handle Sporty format: "total=2.5", "hcp=1:0"
        if "=" in specifier:
            return specifier.split("=", 1)[1]
        
        return specifier

    async def run(self, scrape_sporty: bool = True, scrape_pawa: bool = True, force: bool = False, run_engines: bool = True):
        """
        Run the unified scraper.
        
        Args:
            scrape_sporty: Whether to scrape Sportybet
            scrape_pawa: Whether to scrape Betpawa
            force: Force full scrape even if 1X2 odds haven't changed
            run_engines: Run 1UP pricing engines after scraping
        """
        logger.info("=" * 60)
        logger.info("UNIFIED BETTING SCRAPER (SHARED BROWSER MODE)")
        logger.info("=" * 60)
        
        # Connect to database
        self.db.connect()
        
        try:
            # Get enabled tournaments
            tournaments = self.config.get_enabled_tournaments()
            logger.info(f"Enabled tournaments: {len(tournaments)}")

            logger.info("\nSTAGE 1: Tournament Processing")

            # Start shared browser for Sportybet (if needed)
            if scrape_sporty:
                self._browser_manager = SharedBrowserManager()
                await self._browser_manager.start()
                await self._browser_manager.create_page_pool(self.max_sporty_concurrent)
                logger.info("Shared browser ready for all Sportybet tournaments")
            
            try:
                # Process tournaments in parallel batches
                semaphore = asyncio.Semaphore(self.max_tournaments_concurrent)
                
                async def process_tournament(tournament):
                    async with semaphore:
                        await self._process_tournament(tournament, scrape_sporty, scrape_pawa, force)
                
                # Run all tournaments concurrently (limited by semaphore)
                await asyncio.gather(*[
                    process_tournament(t) for t in tournaments
                ])
                
            finally:
                # Close shared browser
                if self._browser_manager:
                    await self._browser_manager.close()
            
            # Print final stats
            self._print_stats()

            # Run 1UP pricing engines on new snapshots
            if run_engines:
                logger.info("\nSTAGE 2: Engine Calculations")
                logger.info("\n" + "=" * 60)
                logger.info("RUNNING 1UP PRICING ENGINES ON NEW SNAPSHOTS")
                logger.info("=" * 60)

                runner = EngineRunner(self.db, self.config)
                engine_results = runner.run_new_snapshots()

                logger.info(f"\nEngine calculations complete:")
                logger.info(f"  Sessions processed: {engine_results.get('sessions', 0)}")
                logger.info(f"  Events processed: {engine_results['events']}")
                logger.info(f"  Total calculations: {engine_results['calculations']}")
            
        finally:
            self.db.close()

    async def _check_betpawa_changes_for_tournament(self, tournament: dict, force: bool) -> dict:
        """
        Check BetPawa 1x2 odds for all events in tournament and identify changed events.

        This method fetches BetPawa events and 1x2 odds, then checks which events have
        changed 1x2 odds compared to the last market snapshot. Only changed events are
        returned for full multi-bookmaker scraping.

        Args:
            tournament: Tournament dict with pawa_competition_id
            force: If True, return all events regardless of change status

        Returns:
            Dict mapping sportradar_id -> {
                'home_odds': float,
                'draw_odds': float,
                'away_odds': float,
                'event': PawaEvent object
            }
        """
        logger.info(f"\n--- BetPawa Change Detection [{tournament['name']}] ---")

        changed_events = {}

        if not tournament.get("pawa_competition_id"):
            logger.warning(f"No BetPawa competition ID for {tournament['name']}, skipping change detection")
            return changed_events

        try:
            async with BetpawaEventsScraper() as events_scraper:
                # Fetch events
                tourney = await events_scraper.fetch_competition_events(
                    competition_id=tournament["pawa_competition_id"],
                    category_id=tournament.get("pawa_category_id", "2"),
                    competition_name=tournament["name"],
                )

                if not tourney or not tourney.events:
                    logger.warning(f"No BetPawa events found for {tournament['name']}")
                    return changed_events

                logger.info(f"[BetPawa Change Detection] Found {len(tourney.events)} events")

                # Fetch 1x2 markets for each event to check for changes
                async with BetpawaMarketsScraper(enabled_market_ids=["3743"]) as markets_scraper:
                    for event in tourney.events:
                        if not event.sportradar_id:
                            continue

                        # Fetch 1x2 market (market_type_id = 3743)
                        markets = await markets_scraper.fetch_event_markets(event.event_id)

                        # Extract 1x2 odds
                        odds_1x2 = None
                        for market in markets:
                            if market.market_type_id == "3743" and not market.handicap:
                                if len(market.prices) >= 3:
                                    odds_1x2 = (
                                        market.prices[0].price,
                                        market.prices[1].price,
                                        market.prices[2].price,
                                    )
                                    break

                        if not odds_1x2:
                            continue

                        # Check if odds changed (thread-safe)
                        async with self._db_lock:
                            if force:
                                # Force mode: include all events
                                changed_events[event.sportradar_id] = {
                                    'home_odds': odds_1x2[0],
                                    'draw_odds': odds_1x2[1],
                                    'away_odds': odds_1x2[2],
                                    'event': event,
                                }
                            else:
                                # Check if 1x2 odds changed from last snapshot
                                changed = self.db.check_1x2_odds_changed(
                                    sportradar_id=event.sportradar_id,
                                    bookmaker="pawa",
                                    home_odds=odds_1x2[0],
                                    draw_odds=odds_1x2[1],
                                    away_odds=odds_1x2[2],
                                )

                                if changed:
                                    changed_events[event.sportradar_id] = {
                                        'home_odds': odds_1x2[0],
                                        'draw_odds': odds_1x2[1],
                                        'away_odds': odds_1x2[2],
                                        'event': event,
                                    }

                logger.info(f"[BetPawa Change Detection] {len(tourney.events)} events found, {len(changed_events)} have 1x2 changes")

        except Exception as e:
            logger.error(f"BetPawa change detection error [{tournament['name']}]: {e}")

        return changed_events

    async def _process_tournament(self, tournament: dict, scrape_sporty: bool, scrape_pawa: bool, force: bool):
        """
        Process a single tournament with BetPawa-first sequential flow.

        Flow:
        1. BetPawa change detection: Check 1x2 odds for all events
        2. If no changes (and not force): Skip tournament
        3. If changes: Scrape all bookmakers for changed events only
        """
        logger.info(f"\n{'='*60}")
        logger.info(f"Tournament: {tournament['name']}")
        logger.info(f"  Sporty ID: {tournament['id']}")
        logger.info(f"  Pawa Competition ID: {tournament.get('pawa_competition_id')}")
        # Log Bet9ja group id and enabled Bet9ja mappings for clarity
        bet9ja_gid = tournament.get('bet9ja_group_id')
        logger.info(f"  Bet9ja Group ID: {bet9ja_gid}")
        # collect mapped Bet9ja market names that are enabled in config
        try:
            bj_names = set()
            for v in (self.bet9ja_market_map or {}).values():
                if isinstance(v, dict):
                    name = v.get('market_name')
                    if name:
                        bj_names.add(name)
                elif isinstance(v, list):
                    for it in v:
                        if isinstance(it, dict) and it.get('market_name'):
                            bj_names.add(it.get('market_name'))
            # filter to enabled unified markets
            bj_enabled = [n for n in sorted(bj_names) if n.upper() in self.enabled_market_names]
        except Exception:
            bj_enabled = []
        logger.info(f"  Bet9ja enabled mapped markets ({len(bj_enabled)}): {', '.join(bj_enabled) if bj_enabled else 'none'}")
        logger.info(f"{'='*60}")

        # Save tournament to DB (thread-safe)
        async with self._db_lock:
            self.db.upsert_tournament(
                tournament_id=tournament["id"],
                name=tournament["name"],
                sport=tournament.get("sport", "football"),
                category_id=tournament.get("category_id"),
                pawa_category_id=tournament.get("pawa_category_id"),
                pawa_competition_id=tournament.get("pawa_competition_id"),
                enabled=tournament.get("enabled", True),
            )
            logger.info(f"Tournament synced to database: {tournament['name']}")

        # PHASE 1: BetPawa Change Detection (runs first)
        changed_events = await self._check_betpawa_changes_for_tournament(tournament, force)

        # Early return if no changes detected
        if not changed_events and not force:
            logger.info(f"[{tournament['name']}] No BetPawa 1x2 changes, skipping tournament")
            return

        # Update BetPawa cached 1x2 odds in DB for all changed events
        async with self._db_lock:
            for sportradar_id, event_data in changed_events.items():
                self.db.update_1x2_odds(
                    sportradar_id=sportradar_id,
                    bookmaker="pawa",
                    home_odds=event_data['home_odds'],
                    draw_odds=event_data['draw_odds'],
                    away_odds=event_data['away_odds'],
                )

        # PHASE 2: Conditional Multi-Bookmaker Scraping (only for changed events)
        changed_sportradar_ids = set(changed_events.keys())
        logger.info(f"[{tournament['name']}] Triggering multi-bookmaker scraping for {len(changed_sportradar_ids)} changed events")

        # Build list of tasks to run in parallel with filter
        tasks = []
        if scrape_sporty:
            tasks.append(self._scrape_sportybet(tournament, force=force, filter_sportradar_ids=changed_sportradar_ids))

        if scrape_pawa and tournament.get("pawa_competition_id"):
            tasks.append(self._scrape_betpawa(tournament, force=force, filter_sportradar_ids=changed_sportradar_ids))

        # Bet9ja scraping (use EXTID as sportradar equivalent)
        if tournament.get("bet9ja_group_id"):
            tasks.append(self._scrape_bet9ja(tournament, force=force, filter_sportradar_ids=changed_sportradar_ids))

        summaries = []
        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for r in results:
                if isinstance(r, Exception):
                    logger.error(f"Error during scraper task: {r}")
                    continue
                if isinstance(r, dict):
                    summaries.append(r)

        # Tournament-level summary: aggregate per-source stats
        if summaries:
            # initialize
            sporty = next((s for s in summaries if s.get('source') == 'sporty'), {})
            pawa = next((s for s in summaries if s.get('source') == 'pawa'), {})
            bet9ja = next((s for s in summaries if s.get('source') == 'bet9ja'), {})

            logger.info(f"[{tournament['name']}] Scrape summary:")
            logger.info(f"  Sporty: events_found={sporty.get('events_found',0)}, events_scraped={sporty.get('events_scraped',0)}, markets_saved={sporty.get('markets_saved',0)}")
            logger.info(f"  Pawa:   events_found={pawa.get('events_found',0)}, events_scraped={pawa.get('events_scraped',0)}, markets_saved={pawa.get('markets_saved',0)}")
            logger.info(f"  Bet9ja: events_found={bet9ja.get('events_found',0)}, events_scraped={bet9ja.get('events_scraped',0)}, markets_saved={bet9ja.get('markets_saved',0)}")

        # PHASE 3: Snapshot creation (unchanged)
        async with self._db_lock:
            session_ids = self.db.create_snapshots_for_matched_events(tournament["id"])
            if session_ids:
                logger.info(f"[{tournament['name']}] Created {len(session_ids)} match snapshots")

    async def _scrape_sportybet(self, tournament: dict, force: bool = False, filter_sportradar_ids: Optional[set] = None):
        """
        Scrape events and markets from Sportybet using shared browser.

        Args:
            tournament: Tournament dict
            force: Force scrape (unused, kept for compatibility)
            filter_sportradar_ids: If provided, only scrape events with these sportradar IDs
        """
        logger.info(f"\n--- Scraping Sportybet [{tournament['name']}] ---")

        events_to_scrape = []
        tourney = None

        try:
            # Create a new page for events scraping from shared browser
            events_page = await self._browser_manager.new_page()

            try:
                events_scraper = SportybetEventsScraper(page=events_page)
                await events_scraper.start()

                # Fetch events
                tourney = await events_scraper.fetch_tournament_events(
                    tournament_id=tournament["id"],
                    sport=tournament.get("sport", "football"),
                    category_id=tournament.get("category_id", "sr:category:4"),
                )

                if not tourney or not tourney.events:
                    logger.warning(f"No Sportybet events found for {tournament['name']}")
                    return

                logger.info(f"[Sporty {tournament['name']}] Found {len(tourney.events)} events")

                # Store events and apply filter (thread-safe)
                async with self._db_lock:
                    for event in tourney.events:
                        self.db.upsert_sporty_event(
                            sportradar_id=event.sportradar_id,
                            home_team=event.home_team,
                            away_team=event.away_team,
                            start_time=event.start_time,
                            tournament_name=tourney.name,
                            sporty_event_id=event.event_id,
                            sporty_tournament_id=tournament["id"],
                            market_count=event.market_count,
                        )

                        # Apply filter: only scrape events in filter set
                        if filter_sportradar_ids is None or event.sportradar_id in filter_sportradar_ids:
                            events_to_scrape.append(event)

                # Log filtering if applied
                if filter_sportradar_ids is not None:
                    logger.info(f"[Sporty {tournament['name']}] Filtering to {len(events_to_scrape)} changed events (from BetPawa trigger)")

            finally:
                # Close the events page
                await self._browser_manager.close_page(events_page)

            # Fetch markets for events
            if not events_to_scrape:
                logger.info(f"[Sporty {tournament['name']}] No events need market scraping")
                return {'source': 'sporty', 'events_found': len(tourney.events) if tourney else 0, 'events_scraped': 0, 'markets_saved': 0}

            # Fetch markets in parallel using page pool
            results = await self._fetch_sporty_markets_parallel(events_to_scrape, tournament['name'])
            return {'source': 'sporty', 'events_found': len(tourney.events) if tourney else 0, 'events_scraped': len(events_to_scrape), 'markets_saved': results.get('markets_scraped', 0)}

        except Exception as e:
            logger.error(f"Sportybet scraping error [{tournament['name']}]: {e}")
            return {'source': 'sporty', 'events_found': 0, 'events_scraped': 0, 'markets_saved': 0}
    
    def _extract_sporty_1x2_odds(self, markets: list) -> tuple:
        """Extract 1X2 odds from Sportybet markets."""
        for market in markets:
            if str(market.id) == "1" and not market.specifier:
                if len(market.outcomes) >= 3:
                    try:
                        return (
                            float(market.outcomes[0].get("odds", 0)),
                            float(market.outcomes[1].get("odds", 0)),
                            float(market.outcomes[2].get("odds", 0)),
                        )
                    except (ValueError, TypeError):
                        pass
        return None

    async def _fetch_sporty_markets_parallel(self, events: list, tournament_name: str) -> dict:
        """
        Fetch markets for multiple events in parallel using page pool.

        Args:
            events: List of events to fetch markets for (already filtered)
            tournament_name: Name of the tournament (for logging)

        Returns:
            Dict with markets_scraped count
        """
        results = {
            'markets_scraped': 0,
        }
        results_lock = asyncio.Lock()

        async def fetch_single_event(event):
            """Fetch markets for a single event using a page from the pool."""
            nonlocal results

            # Acquire a page from the pool
            page = await self._browser_manager.acquire_page()

            try:
                # Create scraper for this page
                scraper = SportybetMarketsScraper(
                    enabled_market_ids=self.sporty_market_ids,
                    page=page
                )
                await scraper.start()

                logger.info(f"[Sporty] Fetching: {event.home_team} vs {event.away_team}")

                markets = await scraper.fetch_event_markets(event.event_id)

                if not markets:
                    logger.warning(f"[Sporty] No markets found for {event.home_team}")
                    return

                # Store each market in markets table (thread-safe)
                async with self._db_lock:
                    event_markets_count = 0
                    for market in markets:
                        market_info = self.market_mapping.get(str(market.id))
                        if not market_info:
                            continue
                        
                        # Outcomes are already dicts from API
                        outcomes = [
                            {"desc": o.get("desc", ""), "odds": o.get("odds")}
                            for o in market.outcomes
                        ]
                        
                        # Normalize specifier
                        specifier = self._normalize_specifier(market.specifier or "")
                        
                        # Store in markets table (snapshots created after scraping completes)
                        self.db.upsert_market(
                            sportradar_id=event.sportradar_id,
                            market_name=market_info["name"],
                            specifier=specifier,
                            sporty_market_id=str(market.id),
                            sporty_outcomes=outcomes,
                        )
                        
                        event_markets_count += 1

                async with results_lock:
                    results['markets_scraped'] += event_markets_count

                # Log only the mapped/saved market count for this event
                logger.info(f"[Sporty] {event.home_team}: mapped & saved {event_markets_count} markets")
                    
            except Exception as e:
                logger.error(f"[Sporty] Error fetching {event.home_team}: {e}")
            finally:
                # Release page back to pool
                await self._browser_manager.release_page(page)
        
        # Fetch all events in parallel (limited by page pool size)
        logger.info(f"[Sporty {tournament_name}] Fetching {len(events)} events with {self.max_sporty_concurrent} concurrent pages")
        await asyncio.gather(*[fetch_single_event(event) for event in events])
        
        return results

    async def _scrape_betpawa(self, tournament: dict, force: bool = False, filter_sportradar_ids: Optional[set] = None):
        """
        Scrape events and markets from Betpawa with parallel HTTP requests.

        Args:
            tournament: Tournament dict
            force: Force scrape (unused, kept for compatibility)
            filter_sportradar_ids: If provided, only scrape events with these sportradar IDs
        """
        logger.info(f"\n--- Scraping Betpawa [{tournament['name']}] ---")

        events_to_scrape = []

        try:
            async with BetpawaEventsScraper() as events_scraper:
                # Fetch events
                tourney = await events_scraper.fetch_competition_events(
                    competition_id=tournament["pawa_competition_id"],
                    category_id=tournament.get("pawa_category_id", "2"),
                    competition_name=tournament["name"],
                )

                if not tourney or not tourney.events:
                    logger.warning(f"No Betpawa events found for {tournament['name']}")
                    return {'source': 'pawa', 'events_found': 0, 'events_scraped': 0, 'markets_saved': 0}

                logger.info(f"[Pawa {tournament['name']}] Found {len(tourney.events)} events")

                # Store events and apply filter (thread-safe)
                async with self._db_lock:
                    for event in tourney.events:
                        if not event.sportradar_id:
                            logger.warning(f"  Event without Sportradar ID: {event.name}")
                            continue

                        self.db.upsert_pawa_event(
                            sportradar_id=event.sportradar_id,
                            home_team=event.home_team,
                            away_team=event.away_team,
                            start_time=event.start_time,
                            tournament_name=tourney.name,
                            pawa_event_id=event.event_id,
                            pawa_competition_id=tournament["pawa_competition_id"],
                            market_count=event.total_market_count,
                        )

                        # Apply filter: only scrape events in filter set
                        if filter_sportradar_ids is None or event.sportradar_id in filter_sportradar_ids:
                            events_to_scrape.append(event)

                    events_found = len(tourney.events)

                # Log filtering if applied
                if filter_sportradar_ids is not None:
                    logger.info(f"[Pawa {tournament['name']}] Filtering to {len(events_to_scrape)} changed events (from BetPawa trigger)")
            
            # Fetch markets for all events IN PARALLEL
            async with BetpawaMarketsScraper(
                enabled_market_ids=self.pawa_market_ids
            ) as markets_scraper:
                
                # Semaphore to limit concurrent requests
                sem = asyncio.Semaphore(self.max_pawa_concurrent)

                saved_total = 0

                async def fetch_and_store_event_markets(event):
                    """Fetch and store markets for a single event."""
                    nonlocal saved_total
                    if not event.sportradar_id:
                        return

                    async with sem:
                        logger.info(f"[Pawa] Fetching: {event.home_team} vs {event.away_team}")

                        markets = await markets_scraper.fetch_event_markets(event.event_id)

                        if not markets:
                            logger.warning(f"[Pawa] No markets for {event.home_team}")
                            return

                        # Store each market in markets table (thread-safe)
                        async with self._db_lock:
                            saved_count = 0
                            for market in markets:
                                market_info = self._get_market_info_by_pawa_id(market.market_type_id)
                                if not market_info:
                                    continue
                                
                                # Calculate specifier from handicap
                                specifier = ""
                                if market_info.get("has_specifier") and market.handicap:
                                    try:
                                        scale = market_info.get("pawa_handicap_scale", 4)
                                        goal_line = float(market.handicap) / scale
                                        specifier = str(goal_line)
                                    except (ValueError, TypeError):
                                        specifier = market.handicap
                                
                                # Convert outcomes
                                outcomes = [
                                    {"name": p.display_name, "odds": p.price}
                                    for p in market.prices
                                ]
                                
                                # Store in markets table
                                self.db.upsert_market(
                                    sportradar_id=event.sportradar_id,
                                    market_name=market_info["name"],
                                    specifier=specifier,
                                    pawa_market_id=market.market_type_id,
                                    pawa_outcomes=outcomes,
                                )
                                saved_count += 1
                        # accumulate saved counts
                        saved_total += saved_count
                
                # Fetch all events in parallel
                await asyncio.gather(*[
                    fetch_and_store_event_markets(event) for event in events_to_scrape
                ])

                return {'source': 'pawa', 'events_found': events_found, 'events_scraped': len(events_to_scrape), 'markets_saved': saved_total}

                # Note: individual event logs will report mapped/saved counts
            
        except Exception as e:
            logger.error(f"Betpawa scraping error [{tournament['name']}]: {e}")
            return {'source': 'pawa', 'events_found': 0, 'events_scraped': 0, 'markets_saved': 0}

    async def _scrape_bet9ja(self, tournament: dict, force: bool = False, filter_sportradar_ids: Optional[set] = None):
        """
        Scrape events from Bet9ja and upsert using EXTID as sportradar_id.

        Args:
            tournament: Tournament dict
            force: Force scrape (unused, kept for compatibility)
            filter_sportradar_ids: If provided, only scrape events with these sportradar IDs
        """
        logger.info(f"\n--- Scraping Bet9ja [{tournament['name']}] ---")

        group_id = tournament.get("bet9ja_group_id")
        if not group_id:
            logger.debug("No Bet9ja group id configured for tournament")
            return

        try:
            events_to_scrape = []

            async with Bet9jaEventsScraper() as scraper:
                tourney = await scraper.fetch_group_events(str(group_id))

                if not tourney or not tourney.events:
                    logger.warning(f"No Bet9ja events found for {tournament['name']}")
                    return {'source': 'bet9ja', 'events_found': 0, 'events_scraped': 0, 'markets_saved': 0}

                logger.info(f"[Bet9ja {tournament['name']}] Found {len(tourney.events)} events")
                events_found = len(tourney.events)

                async with self._db_lock:
                    for ev in tourney.events:
                        # Use EXTID as sportradar_id equivalent
                        if not ev.extid:
                            logger.warning(f"  Event without EXTID: {ev.name}")
                            continue

                        sportradar_id = str(ev.extid)

                        self.db.upsert_bet9ja_event(
                            sportradar_id=sportradar_id,
                            home_team=ev.home_team,
                            away_team=ev.away_team,
                            start_time=ev.start_time,
                            tournament_name=tourney.name,
                            bet9ja_event_id=str(ev.event_id),
                            bet9ja_group_id=str(group_id),
                            market_count=ev.market_count,
                        )

                        # Apply filter: only scrape events in filter set
                        if filter_sportradar_ids is None or sportradar_id in filter_sportradar_ids:
                            events_to_scrape.append(ev)

                # Log filtering if applied
                if filter_sportradar_ids is not None:
                    logger.info(f"[Bet9ja {tournament['name']}] Filtering to {len(events_to_scrape)} changed events (from BetPawa trigger)")

            # Fetch markets for all events IN PARALLEL
            async with Bet9jaMarketsScraper() as markets_scraper:
                sem = asyncio.Semaphore(self.max_bet9ja_concurrent)

                # Clear previous Bet9ja columns for events we will scrape to avoid stale mappings
                async with self._db_lock:
                    for ev in events_to_scrape:
                        self.db.clear_bet9ja_columns_for_event(str(ev.extid))

                saved_total = 0

                async def fetch_and_store_event_markets(ev):
                    nonlocal saved_total
                    if not ev.extid:
                        return

                    async with sem:
                        logger.info(f"[Bet9ja] Fetching markets for: {ev.home_team} vs {ev.away_team}")
                        markets = await markets_scraper.fetch_event_markets(str(ev.event_id))

                        if not markets:
                            logger.warning(f"[Bet9ja] No markets for {ev.home_team}")
                            return

                        # Thread-safe DB operations: store each mapped market only
                        async with self._db_lock:
                            saved_count = 0
                            for market in markets:
                                mname = market.get("market_name") or market.get("market_id")
                                spec = market.get("specifier") or ""
                                spec_norm = self._normalize_specifier(spec)

                                raw_outcomes = market.get("outcomes") or []

                                # Map Bet9ja market(s) to unified market names and normalize outcomes
                                mapped = self._map_bet9ja_market(market.get("market_id") or "", mname or "", spec_norm, raw_outcomes)

                                # Upsert one or more market rows (some Bet9ja markets map to multiple unified markets)
                                for mp in mapped:
                                    self.db.upsert_market(
                                        sportradar_id=str(ev.extid),
                                        market_name=mp.get("market_name"),
                                        specifier=mp.get("specifier", spec_norm),
                                        bet9ja_market_id=market.get("market_id"),
                                        bet9ja_outcomes=mp.get("outcomes"),
                                    )
                                    saved_count += 1

                        # accumulate saved counts
                        saved_total += saved_count

                        # Log only the mapped & saved market count for this event
                        logger.info(f"[Bet9ja] {ev.home_team}: mapped & saved {saved_count} markets")

                # Run fetches concurrently
                await asyncio.gather(*[fetch_and_store_event_markets(ev) for ev in events_to_scrape])

                return {'source': 'bet9ja', 'events_found': events_found, 'events_scraped': len(events_to_scrape), 'markets_saved': saved_total}

        except Exception as e:
            logger.error(f"Bet9ja scraping error [{tournament['name']}]: {e}")
            return {'source': 'bet9ja', 'events_found': 0, 'events_scraped': 0, 'markets_saved': 0}
    
    def _extract_pawa_1x2_odds(self, markets: list) -> tuple:
        """Extract 1X2 odds from Betpawa markets."""
        for market in markets:
            if market.market_type_id == "3743" and not market.handicap:
                if len(market.prices) >= 3:
                    return (
                        market.prices[0].price,
                        market.prices[1].price,
                        market.prices[2].price,
                    )
        return None

    def _get_market_info_by_pawa_id(self, pawa_id: str) -> dict:
        """Get market info by Betpawa market ID."""
        for sporty_id, info in self.market_mapping.items():
            if info.get("pawa_id") == pawa_id:
                return info
        return None

    def _normalize_bet9ja_outcomes(self, market_id: str, market_name: str, outcomes: list) -> list:
        """Normalize Bet9ja outcomes into a predictable order and naming.

        - 1X2 markets: order ['1','X','2'] -> home, draw, away
        - Over/Under: order ['O','U'] -> Over, Under
        - BTTS (GGNG / GG): order ['Y','N'] -> Yes, No
        - Asian Handicap: prefer ordering where the first outcome is the home handicap side
        For unknown markets, return outcomes in given order but map keys to desc/odds.
        """
        if not outcomes:
            return []

        # build uppercase key map for robust lookup
        key_map = {}
        for o in outcomes:
            key_field = (o.get('key') or '').strip()
            desc = (o.get('desc') or o.get('name') or '').strip()
            odds = o.get('odds')

            if key_field:
                k = key_field.upper()
            else:
                # infer short key from description
                u = desc.lower()
                if 'over' in u:
                    k = 'O'
                elif 'under' in u:
                    k = 'U'
                elif u in ('gg', 'yes', 'y'):
                    k = 'Y'
                elif u in ('ng', 'no', 'n'):
                    k = 'N'
                else:
                    k = desc.upper()

            key_map[k] = {'desc': desc or k, 'odds': odds}

        def pick(k):
            v = key_map.get(k)
            if v:
                return v
            # fallback: return first available
            items = list(key_map.values())
            return items[0] if items else {'desc': None, 'odds': None}

        mid = (market_id or '').upper()
        mname = (market_name or '').upper()

        # 1X2 standard
        if mid == 'S_1X2' or mname.strip() == '1X2' or mname.startswith('1X2'):
            return [pick('1'), pick('X'), pick('2')]

        # 1UP variant - explicit keys: '11' (1), 'X1' (X), '21' (2)
        if mid.startswith('S_1X21') or '1UP' in mname:
            return [pick('11'), pick('X1'), pick('21')]

        # 2UP variant - explicit keys: '12' (1), 'X2' (X), '22' (2)
        if mid.startswith('S_1X22') or '2UP' in mname:
            return [pick('12'), pick('X2'), pick('22')]

        # Over/Under detection
        if mid.startswith('S_OU') or 'OVER' in mname or 'UNDER' in mname:
            return [pick('O'), pick('U')]

        # BTTS / Goal/No Goal - only map full-time markets (avoid HT/1st/2nd half)
        if (mid == 'S_GGNG' or ('GOAL' in mname and 'NO' in mname) or 'GG/NG' in mname or mname.strip() == 'GOAL / NO GOAL'):
            # exclude half-time variants
            if 'HT' in mid or 'HT' in mname or '1ST' in mname or '2ND' in mname or 'HALF' in mname:
                # fallback to returning raw first two
                keys = list(key_map.keys())
                return [pick(keys[0]), pick(keys[1] if len(keys) > 1 else keys[0])]
            # canonical yes/no keys
            for yes_key in ('Y', 'GG', 'YES'):
                if yes_key in key_map:
                    y = yes_key
                    break
            else:
                y = next((k for k in key_map.keys() if k.startswith('G') or k == 'Y'), list(key_map.keys())[0])

            for no_key in ('N', 'NG', 'NO'):
                if no_key in key_map:
                    n = no_key
                    break
            else:
                n = next((k for k in key_map.keys() if k.startswith('N') or k == 'NO'), next(iter(key_map.keys())))

            return [pick(y), pick(n)]

        # Asian handicap
        if mid.startswith('S_AH') or 'HANDICAP' in mname:
            # return first two outcomes
            keys = list(key_map.keys())
            return [pick(keys[0]), pick(keys[1] if len(keys) > 1 else keys[0])]

        # Default: return first three
        keys = list(key_map.keys())
        return [pick(keys[i]) if i < len(keys) else {'desc': None, 'odds': None} for i in range(min(3, len(keys)))]

    def _map_bet9ja_market(self, market_id: str, market_name: str, specifier: str, raw_outcomes: list) -> list:
        """Map a Bet9ja market to one or more unified markets and normalize outcomes.

        Returns a list of dicts: {market_name, specifier, outcomes}
        """
        mid = (market_id or '').upper()
        mname = (market_name or '').upper()

        # Use explicit per-market mapping registry. This registry is intentionally empty by default
        # to avoid accidental or heuristic mappings. Populate `self.bet9ja_market_map` with entries
        # of the form:
        #   self.bet9ja_market_map['S_1X2'] = {'market_name': '1X2', 'use_normalize': True}
        # or for multiple mappings:
        #   self.bet9ja_market_map['S_HTFTOU'] = [ {'market_name': 'HT/FT', ...}, {'market_name': 'Over/Under', ...} ]

        mapping = None
        if mid in self.bet9ja_market_map:
            mapping = self.bet9ja_market_map[mid]
        elif mname in self.bet9ja_market_map:
            mapping = self.bet9ja_market_map[mname]

        if not mapping:
            logger.debug(f"Skipping unmapped Bet9ja market: {mid} / {market_name}")
            return []

        # If mapping explicitly marks this market as ignored, skip it
        if isinstance(mapping, dict) and mapping.get('ignore'):
            logger.debug(f"Ignoring Bet9ja market per config: {mid} / {market_name}")
            return []
        if isinstance(mapping, list) and all(isinstance(mv, dict) and mv.get('ignore') for mv in mapping):
            logger.debug(f"Ignoring Bet9ja market-per-list per config: {mid} / {market_name}")
            return []

        # If this is an Over/Under family market, only accept specifiers that are whole
        # or halves (.0 or .5). Skip quarter lines (.25/.75) and others.
        def _specifier_is_valid(s: str) -> bool:
            if not s:
                return True
            try:
                f = float(s)
            except Exception:
                return False
            frac = abs(f - int(f))
            # allow floating rounding tolerance
            if abs(frac - 0.0) < 1e-6 or abs(frac - 0.5) < 1e-6:
                return True
            return False

        # Determine if market belongs to OU family
        is_ou_mid = mid.startswith('S_OU') or mid.startswith('S_OUA')
        is_ou_name = 'OVER' in mname and 'UNDER' in mname or 'O/U' in mname or 'O U' in mname
        if (is_ou_mid or is_ou_name):
            # if specifier invalid (e.g., 3.75) skip mapping
            if specifier and not _specifier_is_valid(specifier):
                logger.debug(f"Skipping OU line with non .0/.5 specifier: {mid} / {market_name} @ {specifier}")
                return []

        # Normalize mapping entries to a list
        mappings = mapping if isinstance(mapping, list) else [mapping]
        results = []
        for m in mappings:
            use_norm = m.get('use_normalize', True)

            # If a specific key order is supplied, prefer it (match by explicit 'key' or by desc pattern)
            key_order = m.get('key_order')
            if key_order and isinstance(key_order, (list, tuple)):
                # Build a lookup from raw outcomes
                lookup = {}
                for o in raw_outcomes:
                    k = (o.get('key') or '').strip().upper()
                    desc = (o.get('desc') or o.get('name') or '').strip()
                    odds = o.get('odds')
                    if k:
                        lookup[k] = {'desc': desc or k, 'odds': odds}
                    else:
                        # also allow matching by short tokens in desc
                        lookup[desc.upper()] = {'desc': desc or None, 'odds': odds}

                outcomes = []
                for kk in key_order:
                    kk_u = kk.upper()
                    if kk_u in lookup:
                        outcomes.append(lookup[kk_u])
                    else:
                        # try to find by desc containing the numeric part (e.g., "X - 1UP")
                        found = None
                        for k2, v2 in lookup.items():
                            if kk_u in k2 or kk_u in (v2.get('desc') or '').upper():
                                found = v2
                                break
                        if found:
                            outcomes.append(found)
                        else:
                            outcomes.append({'desc': None, 'odds': None})

            elif use_norm:
                outcomes = self._normalize_bet9ja_outcomes(market_id, market_name, raw_outcomes)
            else:
                outcomes = [ {'desc': o.get('desc') or o.get('name'), 'odds': o.get('odds')} for o in raw_outcomes ]

            results.append({
                'market_name': m.get('market_name', mname),
                'specifier': m.get('specifier', specifier),
                'outcomes': outcomes,
            })

        # Filter out any mapped markets that are not enabled in config/markets.yaml
        filtered = []
        for r in results:
            mn = (r.get('market_name') or '').upper()
            if mn in self.enabled_market_names:
                filtered.append(r)
            else:
                logger.debug(f"Skipping Bet9ja mapped market not enabled in config: {mn}")

        return filtered

    def _print_stats(self):
        """Print database statistics."""
        stats = self.db.get_stats()

        logger.info("\n" + "=" * 60)
        logger.info("DATABASE STATISTICS")
        logger.info("=" * 60)
        logger.info(f"  Tournaments: {stats['total_tournaments']}")
        logger.info(f"  Total Events: {stats['total_events']}")
        logger.info(f"  Matched Events (both bookmakers): {stats['matched_events']}")
        logger.info(f"  Total Markets: {stats['total_markets']}")
        logger.info(f"  Markets with Both Odds: {stats['matched_markets']}")

        logger.info("\n  Match Sessions & Snapshots:")
        logger.info(f"    Match Sessions: {stats['total_sessions']}")
        logger.info(f"    Market Snapshots: {stats['total_snapshots']}")

        logger.info("\n  Markets by Type:")
        for market_name, count in stats['markets_by_type'].items():
            logger.info(f"    {market_name}: {count}")

        # Pipeline summary
        logger.info(f"\nPipeline complete: {stats['total_tournaments']} tournaments, "
                   f"{stats['total_events']} events, {stats['total_snapshots']} snapshots")


async def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Unified Betting Scraper")
    parser.add_argument("--force", "-f", action="store_true", 
                        help="Force full scrape even if 1X2 odds unchanged")
    parser.add_argument("--sporty-only", action="store_true",
                        help="Only scrape Sportybet")
    parser.add_argument("--pawa-only", action="store_true",
                        help="Only scrape Betpawa")
    parser.add_argument("--no-engines", action="store_true",
                        help="Skip running 1UP pricing engines")
    
    args = parser.parse_args()
    
    scrape_sporty = not args.pawa_only
    scrape_pawa = not args.sporty_only
    run_engines = not args.no_engines
    
    scraper = UnifiedScraper()
    await scraper.run(
        scrape_sporty=scrape_sporty, 
        scrape_pawa=scrape_pawa, 
        force=args.force,
        run_engines=run_engines
    )


if __name__ == "__main__":
    asyncio.run(main())
