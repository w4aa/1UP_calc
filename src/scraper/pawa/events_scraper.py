"""
Betpawa Events Scraper - Fetches events from tournament pages.

This module scrapes events from Betpawa using their API endpoint.
Uses the Sportradar widget ID to match events with Sportybet.
"""

import asyncio
import json
import logging
from typing import Optional
from datetime import datetime
from urllib.parse import quote

import httpx

from .config import BASE_URL, EVENTS_API_ENDPOINT, USER_AGENT, DEFAULT_HEADERS
from .models import PawaEvent, PawaTournament

logger = logging.getLogger(__name__)


class BetpawaEventsScraper:
    """
    Scraper for fetching events from Betpawa competitions.
    Uses direct API calls (no browser needed - API is open).
    """

    def __init__(self):
        """Initialize the scraper."""
        self.client: Optional[httpx.AsyncClient] = None

    async def __aenter__(self):
        """Async context manager entry."""
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()

    async def start(self):
        """Start the HTTP client."""
        logger.info("Starting Betpawa events scraper...")
        self.client = httpx.AsyncClient(
            base_url=BASE_URL,
            headers={
                **DEFAULT_HEADERS,
                "User-Agent": USER_AGENT,
            },
            timeout=30.0,
            follow_redirects=True,
        )
        logger.info("Betpawa HTTP client ready")

    async def close(self):
        """Close the HTTP client."""
        if self.client:
            await self.client.aclose()
        logger.info("Betpawa HTTP client closed")

    def _build_query(self, category_id: str, competition_id: str, take: int = 100) -> dict:
        """
        Build the query object for the Betpawa API.
        
        Args:
            category_id: Sport category (e.g., "2" for football)
            competition_id: Competition/tournament ID (e.g., "15598" for AFCON)
            take: Number of events to fetch
            
        Returns:
            Query dict for the API
        """
        return {
            "queries": [
                # Live events
                {
                    "query": {
                        "eventType": "LIVE",
                        "categories": [category_id],
                        "zones": {
                            "competitions": [competition_id]
                        }
                    },
                    "view": {
                        "marketTypes": ["3743"]  # 1X2 market
                    },
                    "take": take,
                    "skip": 0
                },
                # Upcoming events
                {
                    "query": {
                        "eventType": "UPCOMING",
                        "categories": [category_id],
                        "zones": {
                            "competitions": [competition_id]
                        },
                        "hasOdds": True
                    },
                    "view": {
                        "marketTypes": ["3743"]  # 1X2 market
                    },
                    "take": take,
                    "skip": 0
                }
            ]
        }

    async def fetch_competition_events(
        self,
        competition_id: str,
        category_id: str = "2",
        competition_name: str = "",
    ) -> Optional[PawaTournament]:
        """
        Fetch all events for a competition.
        
        Args:
            competition_id: Betpawa competition ID (e.g., "15598")
            category_id: Sport category ID (e.g., "2" for football)
            competition_name: Name for logging
            
        Returns:
            PawaTournament with events or None if failed
        """
        logger.info(f"Fetching Betpawa events for competition: {competition_id} ({competition_name})")
        
        # Build query
        query = self._build_query(category_id, competition_id)
        query_json = json.dumps(query)
        query_encoded = quote(query_json)
        
        # Make API request
        url = f"{EVENTS_API_ENDPOINT}?q={query_encoded}"
        
        try:
            response = await self.client.get(url)
            response.raise_for_status()
            data = response.json()
            
            return self._parse_response(data, competition_id, category_id, competition_name)
            
        except httpx.HTTPError as e:
            logger.error(f"HTTP error fetching Betpawa events: {e}")
            return None
        except Exception as e:
            logger.error(f"Error fetching Betpawa events: {e}")
            return None

    def _parse_response(
        self,
        data: dict,
        competition_id: str,
        category_id: str,
        competition_name: str,
    ) -> Optional[PawaTournament]:
        """Parse API response and extract events."""
        events = []
        
        # Response has "responses" array with LIVE and UPCOMING
        for response_group in data.get("responses", []):
            for event_data in response_group.get("responses", []):
                event = self._parse_event(event_data)
                if event:
                    events.append(event)
        
        if not events:
            logger.warning(f"No Betpawa events found for competition {competition_id}")
        else:
            logger.info(f"Found {len(events)} Betpawa events")
        
        # Get competition name from first event if not provided
        if events and not competition_name:
            competition_name = events[0].competition_name
        
        return PawaTournament(
            competition_id=competition_id,
            name=competition_name,
            category_id=category_id,
            events=events,
        )

    def _parse_event(self, event_data: dict) -> Optional[PawaEvent]:
        """Parse single event from API response."""
        try:
            event_id = event_data.get("id")
            name = event_data.get("name", "")
            
            # Extract Sportradar ID from widgets
            sportradar_id = None
            for widget in event_data.get("widgets", []):
                if widget.get("type") == "SPORTRADAR":
                    sportradar_id = widget.get("id")
                    break
            
            # Parse participants
            participants = event_data.get("participants", [])
            home_team = ""
            away_team = ""
            for p in participants:
                if p.get("position") == 1:
                    home_team = p.get("name", "")
                elif p.get("position") == 2:
                    away_team = p.get("name", "")
            
            # Parse start time
            start_time_str = event_data.get("startTime", "")
            try:
                start_time = datetime.fromisoformat(start_time_str.replace("Z", "+00:00"))
            except ValueError:
                start_time = datetime.now()
            
            # Get competition/category info
            competition = event_data.get("competition", {})
            category = event_data.get("category", {})
            region = event_data.get("region", {})
            
            # Check if live
            additional_info = event_data.get("additionalInfo", {})
            is_live = additional_info.get("live", False)
            
            return PawaEvent(
                event_id=event_id,
                sportradar_id=sportradar_id,
                name=name,
                home_team=home_team,
                away_team=away_team,
                start_time=start_time,
                competition_id=competition.get("id", ""),
                competition_name=competition.get("name", ""),
                category_id=category.get("id", ""),
                category_name=category.get("name", ""),
                region_id=region.get("id"),
                region_name=region.get("name"),
                total_market_count=event_data.get("totalMarketCount", 0),
                is_live=is_live,
                version=event_data.get("version", 0),
            )
            
        except Exception as e:
            logger.error(f"Error parsing Betpawa event: {e}")
            return None
