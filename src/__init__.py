"""
1UP Calculator - Core Package

A sophisticated sports betting analytics platform that scrapes live odds
from multiple bookmakers and calculates fair 1-Up probabilities using
Monte Carlo simulation and Poisson models.

Main Components:
- ConfigLoader: YAML-based configuration management
- DatabaseManager: SQLite database operations
- UnifiedScraper: Multi-bookmaker odds scraping
- EngineRunner: 1UP pricing engine orchestration
"""

__version__ = "1.0.0"
__author__ = "1UP Calculator Team"

# Export commonly used classes for convenience
from src.config import ConfigLoader
from src.db.manager import DatabaseManager
from src.db.models import Event, Market

__all__ = [
    "ConfigLoader",
    "DatabaseManager",
    "Event",
    "Market",
]
