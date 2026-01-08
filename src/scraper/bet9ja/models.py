"""
Models for Bet9ja events/tournaments.
"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional


@dataclass
class Bet9jaEvent:
    event_id: Optional[int]
    extid: Optional[str]
    name: str
    home_team: str
    away_team: str
    start_time: datetime
    tournament_id: Optional[int]
    market_count: int = 0
    is_live: bool = False
    raw: dict = field(default_factory=dict)


@dataclass
class Bet9jaTournament:
    id: str
    name: str = ""
    events: List[Bet9jaEvent] = field(default_factory=list)
