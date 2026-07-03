from datetime import datetime, timedelta, timezone
import logging
import requests
from typing import Dict, List, Any
from config import ODDSPAPI_KEY, BOOKMAKERS, LOOKAHEAD_HOURS, REQUEST_TIMEOUT, RETRY_COUNT
from matching.normalizer import normalize_team_name, normalize_league

ODDSPAPI_BASE_URL = "https://api.oddspapi.io/v1"
log = logging.getLogger(__name__)

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
        self.api_key = api_key
        self.session = requests.Session()
        self.api_calls = 0

    def _headers(self):
        return {"Authorization": f"Bearer {self.api_key}", "x-api-key": self.api_key}

    def _get(self, path: str, params: Dict[str, Any]):
        url = f"{ODDSPAPI_BASE_URL}{path}"
        last_exc = None
        for _ in range(RETRY_COUNT):
            try:
                self.api_calls += 1
                r = self.session.get(url, headers=self._headers(), params=params, timeout=REQUEST_TIMEOUT)
                if r.status_code == 404:
                    return None
                r.raise_for_status()
                return r.json()
            except Exception as exc:
                last_exc = exc
        raise RuntimeError(f"OddsPapi request failed: {last_exc}")

    def fetch_raw_events(self):
        if not self.api_key:
            raise RuntimeError("ODDSPAPI_KEY non configurata")
        now = datetime.now(timezone.utc)
        end = now + timedelta(hours=LOOKAHEAD_HOURS)
        params = {
            "sport": "soccer",
            "from": now.isoformat(),
            "to": end.isoformat(),
        }
        # L'API può esporre naming diversi a seconda del piano; proviamo endpoint comuni.
        for path in ["/odds", "/events", "/sports/soccer/odds"]:
            data = self._get(path, params)
            if data:
                return data.get("data", data.get("events", data)) if isinstance(data, dict) else data
        return []

    def parse_events(self) -> List[Dict[str, Any]]:
        raw_events = self.fetch_raw_events()
        if isinstance(raw_events, dict):
            log.warning("OddsPapi response shape not recognized for events: keys=%s", sorted(raw_events.keys()))
            raw_events = []
        if not isinstance(raw_events, list):
            log.warning("OddsPapi response shape not recognized for events: type=%s", type(raw_events).__name__)
            raw_events = []
        parsed = []
        for ev in raw_events or []:
            if not isinstance(ev, dict):
                log.warning("OddsPapi event ignored because it is %s", type(ev).__name__)
                continue
            event_id = str(ev.get("id") or ev.get("event_id") or ev.get("fixture_id") or "")
            home = ev.get("home_team") or ev.get("home") or ev.get("homeTeam") or ev.get("participants", [{}])[0].get("name", "")
            away = ev.get("away_team") or ev.get("away") or ev.get("awayTeam") or (ev.get("participants", [{}, {}])[1].get("name", "") if len(ev.get("participants", [])) > 1 else "")
            league = normalize_league(ev.get("league") or ev.get("competition") or ev.get("tournament") or "")
            start_time = ev.get("start_time") or ev.get("commence_time") or ev.get("startTime") or ev.get("date") or ""
            odds_rows = self.parse_odds(ev)
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
