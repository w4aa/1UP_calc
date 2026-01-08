"""
Sportybet Markets Scraper - Fetches odds for individual events.

This module scrapes market odds for specific events using the event API endpoint.
"""

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Optional
from urllib.parse import quote

from playwright.async_api import async_playwright, Browser, BrowserContext, Page, Response

logger = logging.getLogger(__name__)

# Sportybet configuration
BASE_URL = "https://www.sportybet.com"
EVENT_API_ENDPOINT = "/api/ng/factsCenter/event"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36"


@dataclass
class SportyMarket:
    """Market data from Sportybet."""
    id: str
    name: str
    desc: str = ""
    specifier: Optional[str] = None
    status: int = 0
    group: str = ""
    outcomes: list = None
    
    def __post_init__(self):
        if self.outcomes is None:
            self.outcomes = []


class SportybetMarketsScraper:
    """
    Scraper for fetching market odds from Sportybet events.
    Uses network interception to capture API responses.
    
    Can operate in two modes:
    1. Standalone: Creates and manages its own browser instance
    2. Shared: Uses an externally provided page (for better performance)
    """

    def __init__(
        self,
        enabled_market_ids: Optional[set[str]] = None,
        headless: bool = True,
        timeout: int = 30000,
        page: Optional[Page] = None,
    ):
        """
        Initialize the scraper.
        
        Args:
            enabled_market_ids: Set of market IDs to filter (None = all markets)
            headless: Run browser in headless mode (ignored if page provided)
            timeout: Default timeout in milliseconds
            page: Optional external page from SharedBrowserManager
        """
        self.enabled_market_ids = enabled_market_ids
        self.headless = headless
        self.timeout = timeout
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = page
        self._playwright = None
        self._captured_response: Optional[dict] = None
        self._external_page = page is not None
        
        if self.enabled_market_ids:
            logger.info(f"Filtering to {len(self.enabled_market_ids)} market types: {sorted(self.enabled_market_ids)}")

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
            logger.info("Using shared browser page for markets")
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
            extra_http_headers={
                "Accept-Language": "en-US,en;q=0.9",
                "clientid": "web",
                "operid": "2",
                "platform": "web",
            },
        )
        
        self.page = await self.context.new_page()
        self.page.set_default_timeout(self.timeout)
        self.page.on("response", self._handle_response)
        
        logger.info("Browser started successfully")

    async def _handle_response(self, response: Response):
        """Handle and capture API responses."""
        if EVENT_API_ENDPOINT in response.url and response.request.method == "GET":
            try:
                if response.ok:
                    self._captured_response = await response.json()
                    logger.debug(f"Captured API response from {response.url}")
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

    async def fetch_event_markets(
        self,
        event_id: str,
        retry_count: int = 0,
        max_retries: int = 2,
    ) -> Optional[list[SportyMarket]]:
        """
        Fetch all markets and odds for a given event.
        
        Args:
            event_id: Event ID (e.g., "sr:match:61624300")
            retry_count: Current retry attempt
            max_retries: Maximum retries
            
        Returns:
            List of SportyMarket objects or None if failed
        """
        logger.info(f"Fetching markets for event: {event_id}")
        
        self._captured_response = None
        
        # Build event page URL
        encoded_event_id = quote(event_id, safe='')
        timestamp = int(time.time() * 1000)
        event_page_url = f"{BASE_URL}/ng/sport/football/sr:category:1/sr:tournament:17/{event_id}"
        
        try:
            await self.page.goto(event_page_url, wait_until="domcontentloaded")
            
            # Wait for API response
            for _ in range(30):
                if self._captured_response:
                    break
                await asyncio.sleep(0.5)
            
            if not self._captured_response:
                # Try direct API call as fallback
                api_url = f"{BASE_URL}{EVENT_API_ENDPOINT}?eventId={encoded_event_id}&productId=3&_t={timestamp}"
                response = await self.page.evaluate(f"""
                    async () => {{
                        try {{
                            const res = await fetch('{api_url}', {{
                                headers: {{
                                    'Accept': '*/*',
                                    'clientid': 'web',
                                    'operid': '2',
                                    'platform': 'web'
                                }}
                            }});
                            return await res.json();
                        }} catch(e) {{
                            return null;
                        }}
                    }}
                """)
                if response:
                    self._captured_response = response
            
            if not self._captured_response:
                if retry_count < max_retries:
                    logger.warning(f"Retrying... ({retry_count + 1}/{max_retries})")
                    await asyncio.sleep(2)
                    return await self.fetch_event_markets(event_id, retry_count + 1, max_retries)
                logger.error("Could not capture API response")
                return None
            
            return self._parse_markets_response(self._captured_response, event_id)
            
        except Exception as e:
            logger.error(f"Error fetching event markets: {e}")
            if retry_count < max_retries:
                await asyncio.sleep(2)
                return await self.fetch_event_markets(event_id, retry_count + 1, max_retries)
            return None

    def _parse_markets_response(self, response: dict, event_id: str) -> Optional[list[SportyMarket]]:
        """Parse API response and extract markets with odds."""
        biz_code = response.get("bizCode")
        if biz_code != 10000:
            logger.error(f"API error: {biz_code}, message: {response.get('message')}")
            return None
        
        data = response.get("data", {})
        markets_data = data.get("markets", [])
        
        if not markets_data:
            logger.warning(f"No markets in response for event {event_id}")
            return None
        
        # Filter by enabled market IDs if configured
        if self.enabled_market_ids:
            markets_data = [m for m in markets_data if m.get("id") in self.enabled_market_ids]
            logger.debug(f"Filtered to {len(markets_data)} markets")
        
        logger.info(f"Found {len(markets_data)} markets for event {event_id}")
        
        markets = []
        for m in markets_data:
            outcomes = m.get("outcomes", [])
            if not outcomes:
                continue
            
            market = SportyMarket(
                id=m.get("id", ""),
                name=m.get("name", ""),
                desc=m.get("desc", ""),
                specifier=m.get("specifier"),
                status=m.get("status", 0),
                group=m.get("group", ""),
                outcomes=outcomes,
            )
            markets.append(market)
        
        logger.info(f"Parsed {len(markets)} markets with odds")
        return markets
