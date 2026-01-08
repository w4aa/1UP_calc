"""
Betpawa configuration constants.
"""

# Betpawa base URL
BASE_URL = "https://www.betpawa.com.gh"

# API endpoints
EVENTS_API_ENDPOINT = "/api/sportsbook/v3/events/lists/by-queries"
EVENT_API_ENDPOINT = "/api/sportsbook/v3/events"

# User agent
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36"

# Default headers for Betpawa API
DEFAULT_HEADERS = {
    "Accept": "*/*",
    "Accept-Language": "en-GB,en-US;q=0.9,en;q=0.8",
    "Content-Type": "application/json",
    "devicetype": "web",
    "x-pawa-brand": "betpawa-ghana",
}
