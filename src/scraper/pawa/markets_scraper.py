"""
Betpawa Markets Scraper - Fetches odds for individual events.

This module scrapes market odds for specific events using the event API endpoint.
"""

import asyncio
import logging
from typing import Optional

import httpx

from .config import BASE_URL, EVENT_API_ENDPOINT, USER_AGENT, DEFAULT_HEADERS
from .models import PawaMarket, PawaPrice

logger = logging.getLogger(__name__)


class BetpawaMarketsScraper:
    """
    Scraper for fetching market odds from Betpawa events.
    Uses direct API calls (no browser needed).
    """

    def __init__(self, enabled_market_ids: Optional[set[str]] = None):
        """
        Initialize the scraper.
        
        Args:
            enabled_market_ids: Set of market type IDs to filter (None = all markets)
        """
        self.client: Optional[httpx.AsyncClient] = None
        self.enabled_market_ids = enabled_market_ids
        
        if self.enabled_market_ids:
            logger.info(f"Betpawa markets filter: {len(self.enabled_market_ids)} market types")

    async def __aenter__(self):
        """Async context manager entry."""
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()

    async def start(self):
        """Start the HTTP client."""
        logger.info("Starting Betpawa markets scraper...")
        self.client = httpx.AsyncClient(
            base_url=BASE_URL,
            headers={
                **DEFAULT_HEADERS,
                "User-Agent": USER_AGENT,
            },
            timeout=30.0,
            follow_redirects=True,
        )
        logger.info("Betpawa markets HTTP client ready")

    async def close(self):
        """Close the HTTP client."""
        if self.client:
            await self.client.aclose()
        logger.info("Betpawa markets HTTP client closed")

    async def fetch_event_markets(
        self,
        event_id: str,
        retry_count: int = 0,
        max_retries: int = 2,
    ) -> Optional[list[PawaMarket]]:
        """
        Fetch all markets and odds for a given event.
        
        Args:
            event_id: Betpawa event ID (e.g., "32228959")
            retry_count: Current retry attempt
            max_retries: Maximum retries
            
        Returns:
            List of PawaMarket objects or None if request failed
        """
        logger.debug(f"Fetching Betpawa markets for event: {event_id}")
        
        url = f"{EVENT_API_ENDPOINT}/{event_id}"
        
        try:
            response = await self.client.get(url)
            response.raise_for_status()
            data = response.json()
            
            return self._parse_markets_response(data, event_id)
            
        except httpx.HTTPError as e:
            logger.error(f"HTTP error fetching Betpawa markets: {e}")
            if retry_count < max_retries:
                logger.warning(f"Retrying... ({retry_count + 1}/{max_retries})")
                await asyncio.sleep(1)
                return await self.fetch_event_markets(event_id, retry_count + 1, max_retries)
            return None
        except Exception as e:
            logger.error(f"Error fetching Betpawa markets: {e}")
            if retry_count < max_retries:
                await asyncio.sleep(1)
                return await self.fetch_event_markets(event_id, retry_count + 1, max_retries)
            return None

    def _parse_markets_response(self, data: dict, event_id: str) -> Optional[list[PawaMarket]]:
        """Parse API response and extract markets with odds."""
        markets_data = data.get("markets", [])
        
        if not markets_data:
            logger.warning(f"No markets in Betpawa response for event {event_id}")
            return None
        
        # Filter by enabled market IDs if configured
        if self.enabled_market_ids:
            markets_data = [
                m for m in markets_data 
                if m.get("marketType", {}).get("id") in self.enabled_market_ids
            ]
            logger.debug(f"Filtered to {len(markets_data)} Betpawa markets")
        
        logger.debug(f"Found {len(markets_data)} Betpawa markets for event {event_id}")
        
        markets = []
        for m in markets_data:
            market_type = m.get("marketType", {})
            rows = m.get("row", [])
            additional_info = m.get("additionalInfo", {})
            
            if not rows:
                continue
            
            # Each row is a different handicap/line variant
            for row in rows:
                prices = self._parse_prices(row.get("prices", []))
                if not prices:
                    continue
                
                # Use raw handicap (scaled by 4: handicap/4 = goal_line)
                # e.g., handicap=10 means 2.5 goals, handicap=6 means 1.5 goals
                handicap_value = row.get("handicap")
                
                market = PawaMarket(
                    market_type_id=market_type.get("id", ""),
                    market_type_name=market_type.get("name", ""),
                    display_name=market_type.get("displayName", ""),
                    row_id=row.get("id", ""),
                    handicap=str(handicap_value) if handicap_value is not None else None,
                    prices=prices,
                    is_boosted=additional_info.get("boosted", False),
                    has_two_up=additional_info.get("twoUp", False),
                )
                markets.append(market)
        
        logger.debug(f"Parsed {len(markets)} Betpawa market rows with odds")
        return markets

    def _parse_prices(self, prices_data: list) -> list[PawaPrice]:
        """Parse price/outcome data from a market row."""
        prices = []
        for p in prices_data:
            if p.get("suspended"):
                continue
            
            price = p.get("price")
            if not price:
                continue
            
            additional_info = p.get("additionalInfo", {})
            
            prices.append(PawaPrice(
                id=p.get("id", ""),
                name=p.get("name", ""),
                display_name=p.get("displayName", ""),
                type_id=p.get("typeId", ""),
                price=float(price),
                suspended=p.get("suspended", False),
                has_two_up=additional_info.get("twoUp", False),
            ))
        
        return prices
