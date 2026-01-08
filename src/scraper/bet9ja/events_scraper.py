"""
Bet9ja Events Scraper - minimal first version to fetch events for a group/tournament.

This implements an async HTTP client that requests the group's events JSON
and returns parsed `Bet9jaTournament` with `Bet9jaEvent` entries.

We only parse event-level metadata (EXTID, DS, STARTDATE, ID) in this first
iteration. Market scraping and matching will come later.
"""

import logging
from datetime import datetime
from typing import Optional, List

import httpx

from .config import BASE_URL, EVENTS_API_ENDPOINT, DEFAULT_HEADERS, DEFAULT_CACHE_VERSION
from .models import Bet9jaEvent, Bet9jaTournament

logger = logging.getLogger(__name__)


class Bet9jaEventsScraper:
    """Simple scraper for Bet9ja group events."""

    def __init__(self):
        self.client: Optional[httpx.AsyncClient] = None

    async def __aenter__(self):
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc, tb):
        await self.close()

    async def start(self):
        logger.info("Starting Bet9ja HTTP client")
        self.client = httpx.AsyncClient(
            base_url=BASE_URL,
            headers={**DEFAULT_HEADERS},
            timeout=30.0,
            follow_redirects=True,
        )

    async def close(self):
        if self.client:
            await self.client.aclose()
            self.client = None
        logger.info("Bet9ja HTTP client closed")

    async def fetch_group_events(self, group_id: str, cache_version: str = DEFAULT_CACHE_VERSION) -> Optional[Bet9jaTournament]:
        """Fetch events for a given GROUPID (tournament).

        Args:
            group_id: GROUPID parameter from Bet9ja (e.g., '170880')
            cache_version: v_cache_version string

        Returns:
            Bet9jaTournament or None on error
        """
        if not self.client:
            await self.start()

        params = {
            "GROUPID": group_id,
            "DISP": "0",
            "GROUPMARKETID": "1",
            "v_cache_version": cache_version,
        }

        url = EVENTS_API_ENDPOINT

        try:
            resp = await self.client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()

            # Response contains top-level D -> E list of events
            d = data.get("D", {})
            events_data: List[dict] = d.get("E", [])

            tournament = Bet9jaTournament(id=group_id)

            for ev in events_data:
                try:
                    event_id = ev.get("ID")
                    extid = ev.get("EXTID")
                    ds = ev.get("DS", "")
                    startdate = ev.get("STARTDATE", "")

                    # Split name into home - away if possible
                    home, away = ("", "")
                    if " - " in ds:
                        parts = ds.split(" - ", 1)
                        home, away = parts[0].strip(), parts[1].strip()
                    else:
                        home = ds

                    # Parse start time (format: YYYY-MM-DD HH:MM:SS)
                    try:
                        start_time = datetime.strptime(startdate, "%Y-%m-%d %H:%M:%S") if startdate else datetime.now()
                    except Exception:
                        start_time = datetime.now()

                    event = Bet9jaEvent(
                        event_id=event_id,
                        extid=extid,
                        name=ds,
                        home_team=home,
                        away_team=away,
                        start_time=start_time,
                        tournament_id=ev.get("GID"),
                        market_count=ev.get("MKNUM", 0),
                        is_live=bool(ev.get("ST") == 2),
                        raw=ev,
                    )

                    tournament.events.append(event)
                except Exception as e:
                    logger.debug(f"Skipping event due to parse error: {e}")
                    continue

            logger.info(f"Fetched {len(tournament.events)} events for group {group_id}")
            return tournament

        except httpx.HTTPError as e:
            logger.error(f"HTTP error fetching Bet9ja events for {group_id}: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error fetching Bet9ja events for {group_id}: {e}")
            return None
