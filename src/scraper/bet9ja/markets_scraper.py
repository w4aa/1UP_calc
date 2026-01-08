"""
Bet9ja Markets Scraper - fetches per-event markets and odds.

Parses the event JSON `O` mapping and `TRANS` translations to produce
market_name, specifier and outcomes list suitable for storing in DB.
"""

import asyncio
import logging
from typing import Optional, Dict, List

import httpx

from .config import BASE_URL, EVENTS_API_ENDPOINT, DEFAULT_HEADERS, DEFAULT_CACHE_VERSION

logger = logging.getLogger(__name__)


class Bet9jaMarketsScraper:
    """Fetch markets for a single Bet9ja event."""

    def __init__(self):
        self.client: Optional[httpx.AsyncClient] = None

    async def __aenter__(self):
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc, tb):
        await self.close()

    async def start(self):
        logger.info("Starting Bet9ja markets HTTP client")
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
        logger.info("Bet9ja markets HTTP client closed")

    async def fetch_event_markets(self, event_id: str, cache_version: str = DEFAULT_CACHE_VERSION) -> Optional[List[Dict]]:
        """Fetch and parse markets for a Bet9ja event.

        Returns a list of dicts: {market_name, specifier, outcomes: [{name, odds}, ...], market_id}
        """
        if not self.client:
            await self.start()

        params = {"EVENTID": event_id, "v_cache_version": cache_version}
        url = "/desktop/feapi/PalimpsestAjax/GetEvent"

        try:
            resp = await self.client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()

            return self._parse_event_response(data)

        except httpx.HTTPError as e:
            logger.error(f"HTTP error fetching Bet9ja event {event_id}: {e}")
            return None
        except Exception as e:
            logger.error(f"Error parsing Bet9ja event {event_id}: {e}")
            return None

    def _parse_event_response(self, data: dict) -> Optional[List[Dict]]:
        """Parse response JSON to markets structure."""
        # Robust extraction: response may have D -> ... or be top-level
        d = data.get("D") or data

        # Try to find event object
        event_obj = None
        if isinstance(d, dict) and "E" in d:
            e_list = d.get("E") or []
            if isinstance(e_list, list) and len(e_list) > 0:
                event_obj = e_list[0]
        elif isinstance(d, dict) and "O" in d:
            event_obj = d

        if not event_obj:
            logger.warning("No event object found in Bet9ja response")
            return None

        o = event_obj.get("O", {}) or {}
        trans = d.get("TRANS", {}) or {}

        if not o:
            logger.warning("No markets (O) found in Bet9ja event response")
            return None

        # Group keys by market base + specifier
        markets: Dict[str, Dict[str, Dict]] = {}

        for key, val in o.items():
            # key examples: S_1X21_11, S_OU@2.5_O
            outcome_key = None
            spec = None
            base = key

            # split outcome (last _)
            if "_" in key:
                base_part, outcome_key = key.rsplit("_", 1)
            else:
                base_part = key

            # handle specifier with @
            if "@" in base_part:
                base, spec = base_part.split("@", 1)
            else:
                base = base_part

            market_id = base  # e.g., S_1X21, S_OU

            markets.setdefault(market_id, {})
            spec_key = spec or ""
            markets[market_id].setdefault(spec_key, {"market_id": market_id, "specifier": spec_key, "outcomes": {}})

            # Store outcome odds and raw key
            markets[market_id][spec_key]["outcomes"][outcome_key] = val

        # Convert grouped structure into list of market dicts
        parsed_markets = []
        for market_id, spec_variants in markets.items():
            # Resolve human-friendly market name from TRANS: try M#<market_id>
            market_name = None
            tkey = f"M#{market_id}"
            mv = trans.get(tkey)
            if isinstance(mv, dict):
                market_name = mv.get("NAME")
            elif isinstance(mv, str):
                market_name = mv

            if not market_name:
                # fallback: strip leading 'S_' and use that
                market_name = market_id.replace("S_", "")

            for spec_key, entry in spec_variants.items():
                outcomes_list = []
                for outcome_key, odds in entry.get("outcomes", {}).items():
                    # Try to resolve outcome label from TRANS: M#<market_id>_<outcome_key>
                    out_label = None
                    out_tkey = f"M#{market_id}_{outcome_key}"
                    if out_tkey in trans:
                        out_label = trans.get(out_tkey)
                    else:
                        # try MCU# variant
                        mcu = f"MCU#{market_id}_{outcome_key}"
                        if mcu in trans:
                            out_label = trans.get(mcu)

                    if isinstance(out_label, dict):
                        out_label = out_label.get("NAME")

                    if out_label is None:
                        out_label = outcome_key

                    # Convert odds to float if possible
                    try:
                        odd_value = float(odds)
                    except Exception:
                        odd_value = None

                    outcomes_list.append({"key": outcome_key, "desc": out_label, "odds": odd_value})

                parsed_markets.append({
                    "market_name": market_name,
                    "specifier": spec_key,
                    "market_id": market_id,
                    "outcomes": outcomes_list,
                })

        logger.info(f"Parsed {len(parsed_markets)} markets from Bet9ja event")
        return parsed_markets
