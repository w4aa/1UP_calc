"""
Database models for unified betting scraper.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class Event:
    """Unified event model for both bookmakers."""
    sportradar_id: str
    home_team: str
    away_team: str
    start_time: datetime
    tournament_name: str
    
    # Sportybet data
    sporty_event_id: Optional[str] = None
    sporty_tournament_id: Optional[str] = None
    sporty_market_count: int = 0
    
    # Betpawa data
    pawa_event_id: Optional[str] = None
    pawa_competition_id: Optional[str] = None
    pawa_market_count: int = 0
    
    # Status
    matched: bool = False
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)


@dataclass
class Market:
    """Unified market model for both bookmakers."""
    sportradar_id: str
    market_name: str
    specifier: str = ""  # e.g., "total=2.5" for O/U
    
    # Sportybet odds
    sporty_market_id: Optional[str] = None
    sporty_outcome_1_name: Optional[str] = None
    sporty_outcome_1_odds: Optional[float] = None
    sporty_outcome_2_name: Optional[str] = None
    sporty_outcome_2_odds: Optional[float] = None
    sporty_outcome_3_name: Optional[str] = None
    sporty_outcome_3_odds: Optional[float] = None
    
    # Betpawa odds
    pawa_market_id: Optional[str] = None
    pawa_outcome_1_name: Optional[str] = None
    pawa_outcome_1_odds: Optional[float] = None
    pawa_outcome_2_name: Optional[str] = None
    pawa_outcome_2_odds: Optional[float] = None
    pawa_outcome_3_name: Optional[str] = None
    pawa_outcome_3_odds: Optional[float] = None
    
    # Metadata
    scraped_at: datetime = field(default_factory=datetime.now)
    
    @property
    def has_both_odds(self) -> bool:
        """Check if both bookmakers have odds for this market."""
        return (
            self.sporty_outcome_1_odds is not None and 
            self.pawa_outcome_1_odds is not None
        )
    
    @property
    def odds_difference(self) -> Optional[float]:
        """Calculate the max odds difference between bookmakers."""
        if not self.has_both_odds:
            return None
        
        diffs = []
        if self.sporty_outcome_1_odds and self.pawa_outcome_1_odds:
            diffs.append(abs(self.sporty_outcome_1_odds - self.pawa_outcome_1_odds))
        if self.sporty_outcome_2_odds and self.pawa_outcome_2_odds:
            diffs.append(abs(self.sporty_outcome_2_odds - self.pawa_outcome_2_odds))
        if self.sporty_outcome_3_odds and self.pawa_outcome_3_odds:
            diffs.append(abs(self.sporty_outcome_3_odds - self.pawa_outcome_3_odds))
        
        return max(diffs) if diffs else None
