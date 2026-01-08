"""
Data models for Betpawa scraper.
"""

from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime


@dataclass
class PawaParticipant:
    """Betpawa event participant (team)."""
    id: str
    name: str
    position: int  # 1 = home, 2 = away


@dataclass
class PawaEvent:
    """Betpawa event data."""
    event_id: str                          # Betpawa event ID
    sportradar_id: Optional[str]           # Sportradar ID for matching with Sportybet
    name: str                              # Event name (e.g., "Algeria - Congo DR")
    home_team: str
    away_team: str
    start_time: datetime
    competition_id: str                    # Betpawa competition ID
    competition_name: str
    category_id: str                       # Betpawa category ID (sport)
    category_name: str
    region_id: Optional[str] = None
    region_name: Optional[str] = None
    total_market_count: int = 0
    is_live: bool = False
    version: int = 0


@dataclass
class PawaTournament:
    """Betpawa tournament/competition with events."""
    competition_id: str
    name: str
    category_id: str
    events: list[PawaEvent] = field(default_factory=list)


@dataclass
class PawaPrice:
    """Betpawa market price/outcome."""
    id: str
    name: str           # "1", "X", "2"
    display_name: str
    type_id: str
    price: float
    suspended: bool = False
    has_two_up: bool = False


@dataclass
class PawaMarket:
    """Betpawa market with prices."""
    market_type_id: str
    market_type_name: str
    display_name: str
    row_id: str
    handicap: Optional[str] = None     # Raw or formatted handicap
    prices: list[PawaPrice] = field(default_factory=list)
    is_boosted: bool = False
    has_two_up: bool = False
