from datetime import datetime, timedelta, timezone
from pathlib import Path
import os
import betfairlightweight
import requests
from config import (
    BETFAIR_USERNAME, BETFAIR_PASSWORD, BETFAIR_APP_KEY, BETFAIR_SSOID, BETFAIR_CERT, BETFAIR_KEY,
    BETFAIR_CERT_FILE, BETFAIR_KEY_FILE, BETFAIR_EVENT_TYPE_SOCCER, BETFAIR_LOCALE, BETFAIR_BETTING_API_URL,
    LOOKAHEAD_HOURS, REQUEST_TIMEOUT
)

BETFAIR_MARKETS = {
    "MATCH_ODDS": ["MATCH_ODDS"],
    "MATCH_ODDS_HT": ["HALF_TIME"],
    "BTTS": ["BOTH_TEAMS_TO_SCORE"],
    "DOUBLE_CHANCE": ["DOUBLE_CHANCE"],
    "DRAW_NO_BET": ["DRAW_NO_BET"],
    "CORRECT_SCORE": ["CORRECT_SCORE"],
    "CORRECT_SCORE_HT": ["HALF_TIME_SCORE"],
    "OVER_UNDER_05": ["OVER_UNDER_05"],
    "OVER_UNDER_15": ["OVER_UNDER_15"],
    "OVER_UNDER_25": ["OVER_UNDER_25"],
    "OVER_UNDER_35": ["OVER_UNDER_35"],
    "OVER_UNDER_45": ["OVER_UNDER_45"],
    "OVER_UNDER_55": ["OVER_UNDER_55"],
    "OVER_UNDER_65": ["OVER_UNDER_65"],
    "OVER_UNDER_75": ["OVER_UNDER_75"],
    "OVER_UNDER_85": ["OVER_UNDER_85"],
    "OVER_UNDER_HT_05": ["FIRST_HALF_GOALS_05"],
    "OVER_UNDER_HT_15": ["FIRST_HALF_GOALS_15"],
    "OVER_UNDER_HT_25": ["FIRST_HALF_GOALS_25"],
}

def value(source, key, default=None):
    return source.get(key, default) if isinstance(source, dict) else getattr(source, key, default)

RUNNER_SELECTION_MAP = {
    "the draw": "DRAW", "draw": "DRAW",
    "yes": "YES", "no": "NO",
    "over 0.5 goals": "OVER", "under 0.5 goals": "UNDER",
    "over 1.5 goals": "OVER", "under 1.5 goals": "UNDER",
    "over 2.5 goals": "OVER", "under 2.5 goals": "UNDER",
    "over 3.5 goals": "OVER", "under 3.5 goals": "UNDER",
    "over 4.5 goals": "OVER", "under 4.5 goals": "UNDER",
}

def runner_to_selection(runner_name: str, home: str = "", away: str = ""):
    low = (runner_name or "").lower().strip()
    if low in RUNNER_SELECTION_MAP: return RUNNER_SELECTION_MAP[low]
    if home and low == home.lower().strip(): return "HOME"
    if away and low == away.lower().strip(): return "AWAY"
    compact_score = low.replace(" ", "")
    if "-" in compact_score:
        home_score, away_score = compact_score.split("-", 1)
        if home_score.isdigit() and away_score.isdigit():
            return f"{home_score}:{away_score}"
    if "over" in low: return "OVER"
    if "under" in low: return "UNDER"
    if home and "draw" in low and home.lower().strip() in low: return "1X"
    if away and "draw" in low and away.lower().strip() in low: return "X2"
    if home and away and home.lower().strip() in low and away.lower().strip() in low: return "12"
    if low in {"1x", "x2", "12"}: return low.upper()
    return runner_name.upper().strip()

class BetfairService:
    def __init__(self):
        self.trading = None
        self.api_calls = 0
        self._ensure_certs()

    def _ensure_certs(self):
        cert_path = Path(BETFAIR_CERT_FILE)
        key_path = Path(BETFAIR_KEY_FILE)
        cert_path.parent.mkdir(parents=True, exist_ok=True)
        if BETFAIR_CERT:
            cert_path.write_text(BETFAIR_CERT.replace('\\n', '\n'), encoding='utf-8')
        if BETFAIR_KEY:
            key_path.write_text(BETFAIR_KEY.replace('\\n', '\n'), encoding='utf-8')

    def login(self):
        if not BETFAIR_APP_KEY:
            raise RuntimeError("Variabili Betfair mancanti: BETFAIR_APP_KEY")
        self.trading = betfairlightweight.APIClient(BETFAIR_USERNAME or "", BETFAIR_PASSWORD or "", app_key=BETFAIR_APP_KEY, locale=BETFAIR_LOCALE)
        if BETFAIR_SSOID:
            self.trading.set_session_token(BETFAIR_SSOID.strip())
            return self.trading

        missing = [k for k,v in {
            "BETFAIR_USERNAME": BETFAIR_USERNAME,
            "BETFAIR_PASSWORD": BETFAIR_PASSWORD,
        }.items() if not v]
        if not Path(BETFAIR_CERT_FILE).exists():
            missing.append("BETFAIR_CERT")
        if not Path(BETFAIR_KEY_FILE).exists():
            missing.append("BETFAIR_KEY")
        if missing:
            raise RuntimeError(f"Variabili Betfair mancanti: {', '.join(missing)}")
        self.trading = betfairlightweight.APIClient(BETFAIR_USERNAME, BETFAIR_PASSWORD, app_key=BETFAIR_APP_KEY, cert_files=(BETFAIR_CERT_FILE, BETFAIR_KEY_FILE), locale=BETFAIR_LOCALE)
        self.trading.login()
        return self.trading

    def ensure_login(self):
        if self.trading is None:
            self.login()
        return self.trading

    def keep_alive(self):
        self.ensure_login().keep_alive()

    def call_betting_api(self, operation: str, params: dict):
        trading = self.ensure_login()
        response = requests.post(
            BETFAIR_BETTING_API_URL,
            json={"jsonrpc": "2.0", "method": f"SportsAPING/v1.0/{operation}", "params": params, "id": 1},
            headers={
                "X-Application": BETFAIR_APP_KEY,
                "X-Authentication": trading.session_token or "",
                "Content-Type": "application/json",
            },
            timeout=REQUEST_TIMEOUT,
        )
        if response.status_code != 200:
            if "Cloudflare" in response.text or "Attention Required" in response.text:
                raise RuntimeError(f"Betfair {operation} HTTP {response.status_code}: richiesta bloccata da Cloudflare su {BETFAIR_BETTING_API_URL}")
            raise RuntimeError(f"Betfair {operation} HTTP {response.status_code} su {BETFAIR_BETTING_API_URL}: {response.text[:500]}")
        data = response.json()
        if "error" in data:
            raise RuntimeError(f"Betfair {operation} error: {data['error']}")
        return data.get("result") or []

    def list_market_catalogue(self):
        start = datetime.now(timezone.utc)
        end = start + timedelta(hours=LOOKAHEAD_HOURS)
        market_types = sorted({x for values in BETFAIR_MARKETS.values() for x in values})
        out = []
        for market_type_code in market_types:
            market_filter = betfairlightweight.filters.market_filter(
                event_type_ids=[BETFAIR_EVENT_TYPE_SOCCER],
                market_start_time={"from": start.isoformat(), "to": end.isoformat()},
                market_type_codes=[market_type_code],
            )
            self.api_calls += 1
            catalogues = self.call_betting_api("listMarketCatalogue", {
                "filter": market_filter,
                "marketProjection": ["EVENT", "MARKET_START_TIME", "RUNNER_DESCRIPTION", "MARKET_DESCRIPTION"],
                "sort": "FIRST_TO_START",
                "maxResults": "200",
            })
            out.extend(self.parse_market_catalogues(catalogues))
        return out

    def parse_market_catalogues(self, catalogues):
        out = []
        for c in catalogues:
            description = value(c, "description", {}) or {}
            market_type = value(description, "marketType") or value(description, "market_type")
            internal_market = None
            for k, vals in BETFAIR_MARKETS.items():
                if market_type in vals:
                    internal_market = k
            if not internal_market:
                continue
            event = value(c, "event", {}) or {}
            event_name = value(event, "name", "") or ""
            event_id = value(event, "id", "") or ""
            start_time = str(value(c, "marketStartTime") or value(c, "market_start_time") or "")
            runners = []
            home, away = (event_name.split(' v ', 1) + [''])[:2] if ' v ' in event_name else ('','')
            for r in value(c, "runners", []) or []:
                runner_name = value(r, "runnerName") or value(r, "runner_name") or ""
                runners.append({"selection_id": value(r, "selectionId") or value(r, "selection_id"), "runner_name": runner_name, "selection": runner_to_selection(runner_name, home, away)})
            out.append({"market_id": value(c, "marketId") or value(c, "market_id"), "market": internal_market, "event_name": event_name, "event_id": event_id, "start_time": start_time, "runners": runners})
        return out

    def list_market_books(self, market_ids):
        if not market_ids:
            return []
        self.api_calls += 1
        return self.call_betting_api("listMarketBook", {
            "marketIds": market_ids,
            "priceProjection": {"priceData": ["EX_BEST_OFFERS"]},
        })

    def get_lay_odds_for_catalogues(self, catalogues):
        market_ids = [c["market_id"] for c in catalogues]
        books = []
        for i in range(0, len(market_ids), 40):
            books.extend(self.list_market_books(market_ids[i:i+40]))
        by_id = {value(b, "marketId") or value(b, "market_id"): b for b in books}
        out = []
        for c in catalogues:
            book = by_id.get(c["market_id"])
            if not book: continue
            runner_meta = {r["selection_id"]: r for r in c["runners"]}
            for runner in value(book, "runners", []) or []:
                meta = runner_meta.get(value(runner, "selectionId") or value(runner, "selection_id"))
                if not meta: continue
                ex = value(runner, "ex", {}) or {}
                available = value(ex, "availableToLay") or value(ex, "available_to_lay") or []
                if not available: continue
                best = available[0]
                out.append({"market_id": c["market_id"], "event_id": c["event_id"], "event_name": c["event_name"], "start_time": c["start_time"], "market": c["market"], "selection": meta["selection"], "lay_price": float(value(best, "price")), "lay_size": float(value(best, "size") or 0)})
        return out
