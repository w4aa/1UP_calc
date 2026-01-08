"""
Sportybet Events Scraper using Playwright for browser simulation.

This module scrapes event details from tournament pages on Sportybet.
Uses network interception to capture API responses.
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from playwright.async_api import async_playwright, Browser, BrowserContext, Page, Response

logger = logging.getLogger(__name__)

# Sportybet configuration
BASE_URL = "https://www.sportybet.com"
API_ENDPOINT = "/api/ng/factsCenter/pcEvents"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36"


@dataclass
class SportyEvent:
    """Event data from Sportybet."""
    event_id: str
    sportradar_id: str  # The numeric part of sr:match:XXXXX
    home_team: str
    away_team: str
    start_time: datetime
    tournament_name: str
    tournament_id: str
    category_id: str
    market_count: int = 0
    
    @classmethod
    def from_api_response(cls, data: dict, tournament_name: str = "") -> "SportyEvent":
        """Parse event from API response."""
        event_id = data.get("eventId", "")
        
        # Extract Sportradar ID (numeric part only)
        sportradar_id = event_id.replace("sr:match:", "") if event_id.startswith("sr:match:") else event_id
        
        # Parse start time
        estimate_start = data.get("estimateStartTime", 0)
        start_time = datetime.fromtimestamp(estimate_start / 1000) if estimate_start else datetime.now()
        
        return cls(
            event_id=event_id,
            sportradar_id=sportradar_id,
            home_team=data.get("homeTeamName", ""),
            away_team=data.get("awayTeamName", ""),
            start_time=start_time,
            tournament_name=tournament_name,
            tournament_id=data.get("tournamentId", ""),
            category_id=data.get("categoryId", ""),
            market_count=data.get("totalMarketSize", 0),
        )


@dataclass 
class SportyTournament:
    """Tournament data with events."""
    id: str
    name: str
    category_id: str = ""
    category_name: str = ""
    events: list[SportyEvent] = field(default_factory=list)


class SportybetEventsScraper:
    """
    Scraper for fetching events from Sportybet using browser simulation.
    Uses Playwright to handle anti-bot measures.
    
    Can operate in two modes:
    1. Standalone: Creates and manages its own browser instance
    2. Shared: Uses an externally provided page (for better performance)
    """

    def __init__(self, headless: bool = True, timeout: int = 30000, page: Optional[Page] = None):
        """
        Initialize the scraper.
        
        Args:
            headless: Run browser in headless mode (ignored if page provided)
            timeout: Default page timeout in milliseconds
            page: Optional external page from SharedBrowserManager
        """
        self.headless = headless
        self.timeout = timeout
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = page
        self._playwright = None
        self._captured_response: Optional[dict] = None
        self._external_page = page is not None

    async def __aenter__(self):
        """Async context manager entry."""
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()

    async def start(self):
        """Start the browser and create a new context (only if no external page)."""
        if self._external_page:
            # Using external page - just set up response handler
            self.page.on("response", self._handle_response)
            logger.info("Using shared browser page for events")
            return
            
        logger.info("Starting browser...")
        self._playwright = await async_playwright().start()
        
        self.browser = await self._playwright.chromium.launch(
            headless=self.headless,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
                "--no-sandbox",
            ],
        )
        
        self.context = await self.browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent=USER_AGENT,
            locale="en-US",
            timezone_id="Africa/Lagos",
        )
        
        self.page = await self.context.new_page()
        self.page.set_default_timeout(self.timeout)
        self.page.on("response", self._handle_response)
        
        logger.info("Browser started successfully")

    async def _handle_response(self, response: Response):
        """Handle and capture API responses."""
        if API_ENDPOINT in response.url and response.request.method == "POST":
            try:
                if response.ok:
                    self._captured_response = await response.json()
                    logger.info(f"Captured API response from {response.url}")
            except Exception as e:
                logger.debug(f"Could not parse response: {e}")

    async def close(self):
        """Close the browser and cleanup (only if we own the browser)."""
        if self._external_page:
            # Don't close external page - just remove handler
            logger.debug("Detaching from shared browser page")
            return
            
        logger.info("Closing browser...")
        if self.context:
            await self.context.close()
        if self.browser:
            await self.browser.close()
        if self._playwright:
            await self._playwright.stop()
        logger.info("Browser closed")

    async def fetch_tournament_events(
        self,
        tournament_id: str,
        sport: str = "football",
        category_id: str = "sr:category:4",
        retry_count: int = 0,
        max_retries: int = 2,
    ) -> Optional[SportyTournament]:
        """
        Fetch all events for a given tournament.
        
        Args:
            tournament_id: Tournament ID (e.g., "sr:tournament:270")
            sport: Sport name for URL (e.g., "football")
            category_id: Category ID (e.g., "sr:category:4")
            retry_count: Current retry attempt
            max_retries: Maximum retries
            
        Returns:
            SportyTournament object with events or None if failed
        """
        logger.info(f"Fetching events for tournament: {tournament_id}")
        
        url = f"{BASE_URL}/ng/sport/{sport}/{category_id}/{tournament_id}"
        logger.info(f"Navigating to tournament page: {url}")
        
        self._captured_response = None
        
        try:
            await self.page.goto(url, wait_until="domcontentloaded")
            
            # Wait for API response
            for _ in range(30):
                if self._captured_response:
                    break
                await asyncio.sleep(0.5)
            
            if not self._captured_response:
                # Try scrolling to trigger data load
                await self.page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                for _ in range(10):
                    if self._captured_response:
                        break
                    await asyncio.sleep(0.3)
            
            if not self._captured_response:
                if retry_count < max_retries:
                    logger.warning(f"Retrying... ({retry_count + 1}/{max_retries})")
                    await asyncio.sleep(2)
                    return await self.fetch_tournament_events(
                        tournament_id, sport, category_id, retry_count + 1, max_retries
                    )
                logger.error("Could not capture API response")
                return None
            
            return self._parse_response(self._captured_response, tournament_id)
            
        except Exception as e:
            logger.error(f"Error fetching tournament: {e}")
            if retry_count < max_retries:
                await asyncio.sleep(2)
                return await self.fetch_tournament_events(
                    tournament_id, sport, category_id, retry_count + 1, max_retries
                )
            return None

    def _parse_response(self, response: dict, tournament_id: str) -> Optional[SportyTournament]:
        """Parse API response and extract tournament/event data."""
        biz_code = response.get("bizCode")
        if biz_code != 10000:
            logger.error(f"API error: {response.get('message')}")
            return None
        
        data = response.get("data", [])
        if not data:
            logger.warning("No data in API response")
            return None
        
        tournament_data = data[0]
        
        tournament = SportyTournament(
            id=tournament_id,
            name=tournament_data.get("name", ""),
            category_id=tournament_data.get("categoryId", ""),
            category_name=tournament_data.get("categoryName", ""),
        )
        
        events_data = tournament_data.get("events", [])
        logger.info(f"Found {len(events_data)} events in tournament")
        
        for event_data in events_data:
            try:
                event = SportyEvent.from_api_response(event_data, tournament.name)
                tournament.events.append(event)
            except Exception as e:
                logger.error(f"Failed to parse event: {e}")
                continue
        
        logger.info(f"Successfully parsed {len(tournament.events)} events")
        return tournament
