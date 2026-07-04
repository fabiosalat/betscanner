from dataclasses import dataclass
from typing import Optional
@dataclass
class Event:
    odds_event_id: str; league: str; home_team: str; away_team: str; start_time: str; normalized_home: str; normalized_away: str; id: Optional[int]=None
@dataclass
class BookmakerOdd:
    event_id: int; bookmaker: str; market: str; selection: str; odd: float; oddspapi_market_id: str = ""; oddspapi_outcome_id: str = ""; market_name: str = ""; selection_name: str = ""
@dataclass
class BetfairOdd:
    event_id: int; betfair_market_id: str; market: str; selection: str; lay_price: float; lay_size: float=0.0
@dataclass
class Opportunity:
    type: str; event_id: int; league: str; event_name: str; start_time: str; market: str; selection: str; bookmaker: str; back_odd: float; lay_odd: float; roi: float=0.0; qualifying_loss: float=0.0; lay_stake: float=0.0; liability: float=0.0
