"""
Bet9ja configuration constants.
"""

BASE_URL = "https://sports.bet9ja.com"
EVENTS_API_ENDPOINT = "/desktop/feapi/PalimpsestAjax/GetEventsInGroupV2"
EVENT_API_ENDPOINT = "/desktop/feapi/PalimpsestAjax/GetEvent"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36"
)

DEFAULT_HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-GB,en-US;q=0.9,en;q=0.8",
    "User-Agent": USER_AGENT,
}

# Default cache version used by the site; can be overridden when calling
DEFAULT_CACHE_VERSION = "1.301.2.219"
