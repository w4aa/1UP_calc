"""
Scraper modules for both bookmakers.
"""

from .sporty import SportybetEventsScraper, SportybetMarketsScraper
from .pawa import BetpawaEventsScraper, BetpawaMarketsScraper
from .bet9ja import Bet9jaEventsScraper

__all__ = [
    "SportybetEventsScraper",
    "SportybetMarketsScraper", 
    "BetpawaEventsScraper",
    "BetpawaMarketsScraper",
    "Bet9jaEventsScraper",
]
