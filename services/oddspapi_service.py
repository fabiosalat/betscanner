from datetime import datetime, timedelta, timezone
import logging
from time import monotonic, sleep
import requests
from typing import Dict, List, Any
from config import ODDSPAPI_KEY, BOOKMAKERS, LOOKAHEAD_HOURS, REQUEST_TIMEOUT, RETRY_COUNT, ODDSPAPI_SPORT_ID, ODDSPAPI_LANGUAGE, ODDSPAPI_STATUS_ID, ODDSPAPI_REQUEST_COOLDOWN_SECONDS
from matching.normalizer import normalize_team_name, normalize_league

ODDSPAPI_BASE_URL = "https://api.oddspapi.io"
log = logging.getLogger(__name__)
MAX_FIXTURES_LOOKAHEAD_HOURS = 47
ODDS_BATCH_SIZE = 20
STATIC_ENDPOINTS = {"/v4/sports", "/v4/bookmakers", "/v4/markets", "/v4/languages"}

MARKET_ALIASES = {
    "h2h": "MATCH_ODDS", "match odds": "MATCH_ODDS", "1x2": "MATCH_ODDS",
    "1st half 1x2": "MATCH_ODDS_HT", "half time result": "MATCH_ODDS_HT", "1x2 1st half": "MATCH_ODDS_HT",
    "double chance": "DOUBLE_CHANCE",
    "both teams to score": "BTTS", "btts": "BTTS", "goal/nogoal": "BTTS",
    "both teams to score 1st half": "BTTS_HT", "btts 1st half": "BTTS_HT",
}

SELECTION_ALIASES = {
    "home": "HOME", "1": "HOME", "draw": "DRAW", "x": "DRAW", "away": "AWAY", "2": "AWAY",
    "yes": "YES", "goal": "YES", "no": "NO", "nogoal": "NO",
    "1x": "1X", "x2": "X2", "12": "12",
    "over": "OVER", "under": "UNDER"
}

BOOKMAKER_ALIASES = {
    "sisal": "Sisal IT",
    "sisal it": "Sisal IT",
    "snai": "Snai IT",
    "snai it": "Snai IT",
    "eurobet": "Eurobet IT",
    "eurobet it": "Eurobet IT",
    "planetwin365": "Planetwin365 IT",
    "planet win 365": "Planetwin365 IT",
    "planetwin365 it": "Planetwin365 IT",
    "betflag": "Betflag IT",
    "betflag it": "Betflag IT",
    "bet365": "Bet365 IT",
    "bet365 it": "Bet365 IT",
    "eplay24": "EPLAY24 IT",
    "eplay24 it": "EPLAY24 IT",
}

BOOKMAKER_SLUGS = {
    "Sisal IT": "sisal",
    "Snai IT": "snai",
    "Eurobet IT": "eurobet",
    "Planetwin365 IT": "planetwin365",
    "Betflag IT": "betflag",
    "Bet365 IT": "bet365",
    "EPLAY24 IT": "eplay24",
}

def normalize_market(raw_market: str, line: Any = None, period: str = "") -> str:
    name = (raw_market or "").lower().strip()
    period_l = (period or "").lower()
    if name in MARKET_ALIASES:
        return MARKET_ALIASES[name]
    if "double" in name and "chance" in name: return "DOUBLE_CHANCE"
    if ("both" in name and "score" in name) or "btts" in name:
        return "BTTS_HT" if "half" in name or "1st" in name or "first" in name or period_l in {"1h","first_half"} else "BTTS"
    if "over" in name or "under" in name or "total" in name:
        line_s = str(line or "")
        if not line_s:
            for x in ["0.5","1.5","2.5","3.5","4.5"]:
                if x in name: line_s=x; break
        suffix = line_s.replace(".", "") or "25"
        return f"OVER_UNDER_HT_{suffix}" if "half" in name or "1st" in name or period_l in {"1h","first_half"} else f"OVER_UNDER_{suffix}"
    if "half" in name or "1st" in name or period_l in {"1h","first_half"}: return "MATCH_ODDS_HT"
    return "MATCH_ODDS"

def normalize_selection(raw_selection: str) -> str:
    s = (raw_selection or "").lower().strip().replace(" ", "")
    if s in SELECTION_ALIASES: return SELECTION_ALIASES[s]
    if "over" in s: return "OVER"
    if "under" in s: return "UNDER"
    if "draw" in s: return "DRAW"
    if "yes" in s or "goal" == s: return "YES"
    if "no" in s: return "NO"
    return raw_selection.upper().strip()

def normalize_bookmaker(raw_bookmaker: str) -> str:
    key = (raw_bookmaker or "").lower().strip().replace("_", " ").replace("-", " ")
    return BOOKMAKER_ALIASES.get(key, raw_bookmaker or "")

class OddsPapiService:
    def __init__(self, api_key: str = ODDSPAPI_KEY):
        self.api_key = (api_key or "").strip()
        self.session = requests.Session()
        self.api_calls = 0
        self._markets = None
        self._cache = {}
        self._next_request_at = 0

    def _get(self, path: str, params: Dict[str, Any]):
        url = f"{ODDSPAPI_BASE_URL}{path}"
        last_exc = None
        cache_key = None
        params = {**params, "apiKey": self.api_key}
        if path in STATIC_ENDPOINTS:
            cache_key = (path, tuple(sorted((key, str(value)) for key, value in params.items() if key != "apiKey")))
            if cache_key in self._cache:
                return self._cache[cache_key]
        for _ in range(RETRY_COUNT):
            try:
                wait = self._next_request_at - monotonic()
                if wait > 0:
                    sleep(wait)
                self.api_calls += 1
                r = self.session.get(url, params=params, timeout=REQUEST_TIMEOUT)
                self._next_request_at = monotonic() + ODDSPAPI_REQUEST_COOLDOWN_SECONDS
                if r.status_code == 404:
                    return None
                if r.status_code == 401:
                    raise RuntimeError("ODDSPAPI_KEY non valida o non autorizzata da OddsPapi")
                if r.status_code == 429:
                    raise RuntimeError("OddsPapi rate limit: troppe richieste ravvicinate, attendi il cooldown prima di riprovare")
                r.raise_for_status()
                data = r.json()
                if cache_key is not None:
                    self._cache[cache_key] = data
                return data
            except Exception as exc:
                if str(exc).startswith(("ODDSPAPI_KEY", "OddsPapi rate limit")):
                    raise
                last_exc = exc
        raise RuntimeError(f"OddsPapi request failed: {last_exc}")

    def fetch_raw_events(self):
        if not self.api_key:
            raise RuntimeError("ODDSPAPI_KEY non configurata")
        now = datetime.now(timezone.utc)
        end = now + timedelta(hours=min(LOOKAHEAD_HOURS, MAX_FIXTURES_LOOKAHEAD_HOURS))
        params = {
            "sportId": ODDSPAPI_SPORT_ID,
            "from": now.isoformat(timespec="seconds").replace("+00:00", "Z"),
            "to": end.isoformat(timespec="seconds").replace("+00:00", "Z"),
            "language": ODDSPAPI_LANGUAGE,
            "statusId": ODDSPAPI_STATUS_ID,
            "hasOdds": "true",
            "bookmakers": ",".join(BOOKMAKER_SLUGS[b] for b in BOOKMAKERS if b in BOOKMAKER_SLUGS),
        }
        data = self._get("/v4/fixtures", params)
        if isinstance(data, dict):
            return data.get("data", data.get("fixtures", data.get("events", data)))
        return data or []

    def fetch_fixture_odds(self, fixture_id: str):
        return self._get("/v4/odds", {
            "fixtureId": fixture_id,
            "bookmakers": ",".join(BOOKMAKER_SLUGS[b] for b in BOOKMAKERS if b in BOOKMAKER_SLUGS),
            "language": ODDSPAPI_LANGUAGE,
            "oddsFormat": "decimal",
            "verbosity": 3,
        }) or {}

    def fetch_tournament_odds(self, tournament_ids: List[Any]):
        return self._get("/v4/odds-by-tournaments", {
            "tournamentIds": ",".join(str(t) for t in tournament_ids),
            "bookmakers": ",".join(BOOKMAKER_SLUGS[b] for b in BOOKMAKERS if b in BOOKMAKER_SLUGS),
            "language": ODDSPAPI_LANGUAGE,
            "oddsFormat": "decimal",
            "verbosity": 3,
        }) or []

    def fetch_odds_by_tournaments(self, events: List[Dict[str, Any]]):
        tournament_ids = sorted({ev.get("tournamentId") for ev in events if ev.get("hasOdds") is True and ev.get("tournamentId")})
        odds_by_fixture = {}
        for index in range(0, len(tournament_ids), ODDS_BATCH_SIZE):
            data = self.fetch_tournament_odds(tournament_ids[index:index + ODDS_BATCH_SIZE])
            items = data if isinstance(data, list) else data.get("data", data.get("fixtures", [])) if isinstance(data, dict) else []
            for item in items:
                if isinstance(item, dict) and item.get("fixtureId"):
                    odds_by_fixture[str(item["fixtureId"])] = item
        return odds_by_fixture

    def market_by_id(self, market_id: Any) -> Dict[str, Any]:
        if self._markets is None:
            data = self._get("/v4/markets", {"language": ODDSPAPI_LANGUAGE}) or []
            self._markets = {str(m["marketId"]): m for m in data if isinstance(m, dict) and "marketId" in m}
        return self._markets.get(str(market_id), {})

    def parse_events(self) -> List[Dict[str, Any]]:
        raw_events = self.fetch_raw_events()
        if isinstance(raw_events, dict):
            log.warning("OddsPapi response shape not recognized for events: keys=%s", sorted(raw_events.keys()))
            raw_events = []
        if not isinstance(raw_events, list):
            log.warning("OddsPapi response shape not recognized for events: type=%s", type(raw_events).__name__)
            raw_events = []
        odds_by_fixture = self.fetch_odds_by_tournaments(raw_events)
        parsed = []
        for ev in raw_events or []:
            if not isinstance(ev, dict):
                log.warning("OddsPapi event ignored because it is %s", type(ev).__name__)
                continue
            event_id = str(ev.get("fixtureId") or ev.get("id") or ev.get("event_id") or ev.get("fixture_id") or "")
            home = ev.get("participant1Name") or ev.get("home_team") or ev.get("home") or ev.get("homeTeam") or ev.get("participants", [{}])[0].get("name", "")
            away = ev.get("participant2Name") or ev.get("away_team") or ev.get("away") or ev.get("awayTeam") or (ev.get("participants", [{}, {}])[1].get("name", "") if len(ev.get("participants", [])) > 1 else "")
            league = normalize_league(ev.get("tournamentName") or ev.get("league") or ev.get("competition") or ev.get("tournament") or ev.get("categoryName") or "")
            start_time = ev.get("startTime") or ev.get("start_time") or ev.get("commence_time") or ev.get("date") or ""
            odds_rows = self.parse_odds(odds_by_fixture.get(event_id, ev))
            if event_id and not odds_rows and ev.get("hasOdds") is True and not ev.get("tournamentId"):
                odds_rows = self.parse_odds(self.fetch_fixture_odds(event_id))
            if event_id and home and away:
                parsed.append({
                    "odds_event_id": event_id,
                    "league": league,
                    "home_team": home,
                    "away_team": away,
                    "start_time": start_time,
                    "normalized_home": normalize_team_name(home),
                    "normalized_away": normalize_team_name(away),
                    "odds": odds_rows,
                })
        return parsed

    def parse_odds(self, ev: Dict[str, Any]) -> List[Dict[str, Any]]:
        rows = []
        if isinstance(ev.get("bookmakerOdds"), dict):
            for raw_bookmaker, book in ev["bookmakerOdds"].items():
                if not isinstance(book, dict) or book.get("suspended") is True:
                    continue
                bookmaker = normalize_bookmaker(raw_bookmaker)
                if bookmaker not in BOOKMAKERS:
                    continue
                for market_id, market in (book.get("markets") or {}).items():
                    if not isinstance(market, dict) or market.get("marketActive") is False:
                        continue
                    meta = self.market_by_id(market_id)
                    raw_market = meta.get("marketName") or market.get("bookmakerMarketId") or str(market_id)
                    normalized_market = normalize_market(raw_market, meta.get("handicap"), meta.get("period", ""))
                    outcomes_meta = {str(o.get("outcomeId")): o.get("outcomeName") for o in meta.get("outcomes", []) if isinstance(o, dict)}
                    for outcome_id, outcome in (market.get("outcomes") or {}).items():
                        if not isinstance(outcome, dict):
                            continue
                        selection = normalize_selection(outcomes_meta.get(str(outcome_id)) or "")
                        for player in (outcome.get("players") or {}).values():
                            if not isinstance(player, dict) or player.get("active") is False:
                                continue
                            price = player.get("price")
                            if not selection:
                                selection = normalize_selection(str(player.get("bookmakerOutcomeId") or ""))
                            try:
                                rows.append({"bookmaker": bookmaker, "market": normalized_market, "selection": selection, "odd": float(price)})
                            except Exception:
                                continue
            return rows
        bookmakers = ev.get("bookmakers") or ev.get("sites") or ev.get("odds") or []
        if isinstance(bookmakers, dict):
            bookmakers = [{"title": k, "markets": v} for k, v in bookmakers.items()]
        if not isinstance(bookmakers, list):
            log.warning("OddsPapi bookmakers shape not recognized for event %s: type=%s", ev.get("id") or ev.get("event_id"), type(bookmakers).__name__)
            return rows
        for book in bookmakers:
            if not isinstance(book, dict):
                log.warning("OddsPapi bookmaker ignored because it is %s", type(book).__name__)
                continue
            bookmaker = normalize_bookmaker(book.get("title") or book.get("name") or book.get("bookmaker") or book.get("key") or "")
            if bookmaker not in BOOKMAKERS:
                continue
            markets = book.get("markets") or book.get("bets") or []
            if isinstance(markets, dict):
                markets = [{"key": k, "outcomes": v} for k, v in markets.items()]
            if not isinstance(markets, list):
                log.warning("OddsPapi markets shape not recognized for bookmaker %s: type=%s", bookmaker, type(markets).__name__)
                continue
            for market in markets:
                if not isinstance(market, dict):
                    log.warning("OddsPapi market ignored because it is %s", type(market).__name__)
                    continue
                raw_market = market.get("key") or market.get("name") or market.get("market") or ""
                line = market.get("line") or market.get("handicap") or market.get("total")
                normalized_market = normalize_market(raw_market, line, market.get("period", ""))
                outcomes = market.get("outcomes") or market.get("prices") or market.get("runners") or []
                if isinstance(outcomes, dict):
                    outcomes = [{"name": k, "price": v} for k, v in outcomes.items()]
                if not isinstance(outcomes, list):
                    log.warning("OddsPapi outcomes shape not recognized for market %s: type=%s", raw_market, type(outcomes).__name__)
                    continue
                for out in outcomes:
                    if not isinstance(out, dict):
                        log.warning("OddsPapi outcome ignored because it is %s", type(out).__name__)
                        continue
                    selection = normalize_selection(str(out.get("name") or out.get("selection") or out.get("runner") or ""))
                    price = out.get("price") or out.get("odds") or out.get("decimal")
                    try:
                        price = float(price)
                    except Exception:
                        continue
                    rows.append({"bookmaker": bookmaker, "market": normalized_market, "selection": selection, "odd": price})
        return rows
