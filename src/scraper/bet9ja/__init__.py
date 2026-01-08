"""
Bet9ja scraper package.
"""

from .events_scraper import Bet9jaEventsScraper
from .markets_scraper import Bet9jaMarketsScraper

__all__ = [
    "Bet9jaEventsScraper",
    "Bet9jaMarketsScraper",
]
