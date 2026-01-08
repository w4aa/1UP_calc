"""
Database module for unified betting scraper.
"""

from .manager import DatabaseManager
from .models import Event, Market

__all__ = ["DatabaseManager", "Event", "Market"]
