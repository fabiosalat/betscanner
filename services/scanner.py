import time
import logging
from database.repository import Repository
from database.models import Event, BookmakerOdd, BetfairOdd
from services.oddspapi_service import OddsPapiService
from services.betfair_service import BetfairService
from matching.event_matcher import EventMatcher
from engines.surebet_engine import SurebetEngine
from engines.matched_engine import MatchedEngine

log = logging.getLogger(__name__)

class QuoteScanner:
    def __init__(self):
        self.repo = Repository()
        self.odds = OddsPapiService()
        self.betfair = BetfairService()
        self.matcher = EventMatcher()
        self.surebet = SurebetEngine()
        self.matched = MatchedEngine()

    def refresh(self):
        started = time.time()
        api_calls = 0
        events_count = 0
        try:
            self.repo.clear_current_refresh_data()
            parsed_events = self.odds.parse_events()
            api_calls += self.odds.api_calls
            events_count = len(parsed_events)

            odds_event_payloads = []
            for ev in parsed_events:
                event_id = self.repo.upsert_event(Event(
                    odds_event_id=ev["odds_event_id"],
                    league=ev["league"],
                    home_team=ev["home_team"],
                    away_team=ev["away_team"],
                    start_time=ev["start_time"],
                    normalized_home=ev["normalized_home"],
                    normalized_away=ev["normalized_away"],
                ))
                ev["db_event_id"] = event_id
                odds_event_payloads.append(ev)
                book_rows = [BookmakerOdd(event_id, o["bookmaker"], o["market"], o["selection"], o["odd"]) for o in ev.get("odds", [])]
                self.repo.insert_odds_bulk(book_rows)

            catalogues = self.betfair.list_market_catalogue()
            bf_lays = self.betfair.get_lay_odds_for_catalogues(catalogues)
            api_calls += self.betfair.api_calls

            lay_by_market_id = {}
            for lay in bf_lays:
                lay_by_market_id.setdefault(lay["market_id"], []).append(lay)

            betfair_rows = []
            for ev in odds_event_payloads:
                for market in sorted({o["market"] for o in ev.get("odds", [])}):
                    cached = self.repo.get_event_mapping(ev["odds_event_id"], market)
                    best = None
                    if cached:
                        best = {"market_id": cached["betfair_market_id"], "event_id": cached["betfair_event_id"], "market": market, "confidence_score": cached["confidence_score"]}
                    else:
                        best = self.matcher.find_best(ev, catalogues, market)
                        if best:
                            self.repo.save_event_mapping(ev["odds_event_id"], market, best["market_id"], best.get("event_id", ""), best.get("confidence_score", 0))
                    if not best:
                        continue
                    for lay in lay_by_market_id.get(best["market_id"], []):
                        if lay["market"] != market:
                            continue
                        betfair_rows.append(BetfairOdd(ev["db_event_id"], best["market_id"], market, lay["selection"], lay["lay_price"], lay["lay_size"]))
            self.repo.insert_betfair_odds_bulk(betfair_rows)

            joined = self.repo.get_joined_odds()
            self.repo.clear_opportunities()
            self.repo.save_opportunities(self.surebet.calculate(joined))
            self.repo.save_opportunities(self.matched.calculate(joined))
            self.repo.refresh_stats()
            self.repo.set_cache("last_refresh", {"timestamp": time.time(), "events": events_count, "api_calls": api_calls})
            duration = time.time() - started
            self.repo.save_refresh_history(duration, events_count, api_calls, "ok", "Refresh completato")
            return {"status": "ok", "events": events_count, "api_calls": api_calls, "duration": duration}
        except Exception as exc:
            duration = time.time() - started
            log.exception("Refresh failed")
            self.repo.save_refresh_history(duration, events_count, api_calls, "error", str(exc))
            return {"status": "error", "message": str(exc), "events": events_count, "api_calls": api_calls, "duration": duration}
