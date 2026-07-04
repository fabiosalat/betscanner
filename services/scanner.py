import time
import logging
from database.repository import Repository
from database.models import Event, BookmakerOdd, BetfairOdd
from services.oddspapi_service import OddsPapiService
from services.betfair_service import BetfairService
from matching.event_matcher import EventMatcher
from engines.surebet_engine import SurebetEngine
from engines.matched_engine import MatchedEngine
from config import BETFAIR_ONLY_MODE, ODDSPAPI_RATE_LIMIT_COOLDOWN_SECONDS

log = logging.getLogger(__name__)

class QuoteScanner:
    def __init__(self, bookmakers=None):
        self.repo = Repository()
        self.odds = OddsPapiService(bookmakers=bookmakers)
        self.betfair = BetfairService()
        self.matcher = EventMatcher()
        self.surebet = SurebetEngine()
        self.matched = MatchedEngine()

    def refresh(self):
        started = time.time()
        api_calls = 0
        events_count = 0
        try:
            if BETFAIR_ONLY_MODE:
                catalogues = self.betfair.list_market_catalogue()
                bf_lays = self.betfair.get_lay_odds_for_catalogues(catalogues)
                api_calls += self.betfair.api_calls
                duration = time.time() - started
                stats = {
                    "timestamp": time.time(),
                    "events": 0,
                    "bookmaker_odds": 0,
                    "betfair_markets": len(catalogues),
                    "betfair_lays": len(bf_lays),
                    "matched_lays": 0,
                    "joined_odds": 0,
                    "surebets": 0,
                    "matched": 0,
                    "api_calls": api_calls,
                }
                message = "Refresh Betfair-only completato"
                self.repo.set_cache("last_refresh", stats)
                self.repo.save_refresh_history(duration, 0, api_calls, "ok", message)
                return {"status": "ok", **stats, "duration": duration, "message": message}

            rate_limited_until = float(self.repo.get_cache("oddspapi_rate_limited_until") or 0)
            if rate_limited_until > started:
                wait_seconds = int(rate_limited_until - started)
                message = f"OddsPapi in rate limit: attendi circa {wait_seconds} secondi prima di riprovare"
                return {"status": "rate_limited", "message": message, "events": 0, "api_calls": 0, "duration": 0}

            parsed_events = self.odds.parse_events()
            api_calls += self.odds.api_calls
            events_count = len(parsed_events)
            if not parsed_events:
                duration = time.time() - started
                stats = {
                    "timestamp": time.time(),
                    "events": 0,
                    "bookmaker_odds": 0,
                    "betfair_markets": 0,
                    "betfair_lays": 0,
                    "matched_lays": 0,
                    "joined_odds": 0,
                    "surebets": 0,
                    "matched": 0,
                    "api_calls": api_calls,
                }
                message = "Refresh completato, OddsPapi non ha restituito eventi per le prossime 72 ore"
                self.repo.set_cache("last_refresh", stats)
                self.repo.save_refresh_history(duration, events_count, api_calls, "ok", message)
                return {"status": "ok", **stats, "duration": duration, "message": message}

            self.repo.clear_current_refresh_data()
            odds_event_payloads = []
            bookmaker_odds_count = 0
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
                book_rows = [BookmakerOdd(
                    event_id, o["bookmaker"], o["market"], o["selection"], o["odd"],
                    o.get("oddspapi_market_id", ""), o.get("oddspapi_outcome_id", ""),
                    o.get("market_name", ""), o.get("selection_name", "")
                ) for o in ev.get("odds", [])]
                bookmaker_odds_count += len(book_rows)
                self.repo.insert_odds_bulk(book_rows)

            betfair_error = ""
            try:
                catalogues = self.betfair.list_market_catalogue()
                bf_lays = self.betfair.get_lay_odds_for_catalogues(catalogues)
                api_calls += self.betfair.api_calls
            except Exception as exc:
                api_calls += self.betfair.api_calls
                catalogues = []
                bf_lays = []
                betfair_error = f"Betfair non disponibile: {exc}"
                log.warning(betfair_error, exc_info=True)

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
            surebets = self.surebet.calculate(joined)
            matched = self.matched.calculate(joined)
            self.repo.save_opportunities(surebets)
            self.repo.save_opportunities(matched)
            self.repo.refresh_stats()
            stats = {
                "timestamp": time.time(),
                "events": events_count,
                "bookmaker_odds": bookmaker_odds_count,
                "betfair_markets": len(catalogues),
                "betfair_lays": len(bf_lays),
                "matched_lays": len(betfair_rows),
                "joined_odds": len(joined),
                "surebets": len(surebets),
                "matched": len(matched),
                "api_calls": api_calls,
            }
            self.repo.set_cache("last_refresh", stats)
            duration = time.time() - started
            message = betfair_error or "Refresh completato"
            if not surebets and not matched:
                message = betfair_error or "Refresh completato, nessuna opportunita nei criteri attuali"
            status = "warning" if betfair_error else "ok"
            self.repo.save_refresh_history(duration, events_count, api_calls, status, message)
            return {"status": status, **stats, "duration": duration, "message": message}
        except Exception as exc:
            duration = time.time() - started
            if not api_calls:
                api_calls += getattr(self.odds, "api_calls", 0) + getattr(self.betfair, "api_calls", 0)
            log.exception("Refresh failed")
            if str(exc).startswith("OddsPapi rate limit"):
                self.repo.set_cache("oddspapi_rate_limited_until", time.time() + ODDSPAPI_RATE_LIMIT_COOLDOWN_SECONDS)
            self.repo.save_refresh_history(duration, events_count, api_calls, "error", str(exc))
            return {"status": "error", "message": str(exc), "events": events_count, "api_calls": api_calls, "duration": duration}
