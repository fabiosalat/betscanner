from datetime import datetime, timedelta, timezone
from pathlib import Path
import os
import betfairlightweight
from config import (
    BETFAIR_USERNAME, BETFAIR_PASSWORD, BETFAIR_APP_KEY, BETFAIR_SSOID, BETFAIR_CERT, BETFAIR_KEY,
    BETFAIR_CERT_FILE, BETFAIR_KEY_FILE, BETFAIR_EVENT_TYPE_SOCCER, LOOKAHEAD_HOURS
)

BETFAIR_MARKETS = {
    "MATCH_ODDS": ["MATCH_ODDS"],
    "MATCH_ODDS_HT": ["HALF_TIME"],
    "BTTS": ["BOTH_TEAMS_TO_SCORE"],
    "DOUBLE_CHANCE": ["DOUBLE_CHANCE"],
    "OVER_UNDER_05": ["OVER_UNDER_05"],
    "OVER_UNDER_15": ["OVER_UNDER_15"],
    "OVER_UNDER_25": ["OVER_UNDER_25"],
    "OVER_UNDER_35": ["OVER_UNDER_35"],
    "OVER_UNDER_45": ["OVER_UNDER_45"],
}

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
    if "over" in low: return "OVER"
    if "under" in low: return "UNDER"
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
        self.trading = betfairlightweight.APIClient(BETFAIR_USERNAME or "", BETFAIR_PASSWORD or "", app_key=BETFAIR_APP_KEY)
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
        certs_dir = str(Path(BETFAIR_CERT_FILE).parent)
        self.trading = betfairlightweight.APIClient(BETFAIR_USERNAME, BETFAIR_PASSWORD, app_key=BETFAIR_APP_KEY, certs=certs_dir)
        self.trading.login()
        return self.trading

    def ensure_login(self):
        if self.trading is None:
            self.login()
        return self.trading

    def keep_alive(self):
        self.ensure_login().keep_alive()

    def list_market_catalogue(self):
        trading = self.ensure_login()
        start = datetime.now(timezone.utc)
        end = start + timedelta(hours=LOOKAHEAD_HOURS)
        market_types = sorted({x for values in BETFAIR_MARKETS.values() for x in values})
        market_filter = betfairlightweight.filters.market_filter(
            event_type_ids=[BETFAIR_EVENT_TYPE_SOCCER],
            market_start_time={"from": start.isoformat(), "to": end.isoformat()},
            market_type_codes=market_types,
        )
        self.api_calls += 1
        catalogues = trading.betting.list_market_catalogue(
            filter=market_filter,
            market_projection=["EVENT", "MARKET_START_TIME", "RUNNER_DESCRIPTION", "COMPETITION", "MARKET_DESCRIPTION"],
            max_results=1000,
        )
        out = []
        for c in catalogues:
            market_type = getattr(c.description, 'market_type', None) if getattr(c, 'description', None) else None
            internal_market = None
            for k, vals in BETFAIR_MARKETS.items():
                if market_type in vals:
                    internal_market = k
            if not internal_market:
                continue
            event = getattr(c, 'event', None)
            event_name = getattr(event, 'name', '') if event else ''
            event_id = getattr(event, 'id', '') if event else ''
            start_time = str(getattr(c, 'market_start_time', '') or '')
            runners = []
            home, away = (event_name.split(' v ', 1) + [''])[:2] if ' v ' in event_name else ('','')
            for r in getattr(c, 'runners', []) or []:
                runners.append({"selection_id": r.selection_id, "runner_name": r.runner_name, "selection": runner_to_selection(r.runner_name, home, away)})
            out.append({"market_id": c.market_id, "market": internal_market, "event_name": event_name, "event_id": event_id, "start_time": start_time, "runners": runners})
        return out

    def list_market_books(self, market_ids):
        trading = self.ensure_login()
        if not market_ids:
            return []
        self.api_calls += 1
        price_projection = betfairlightweight.filters.price_projection(price_data=["EX_BEST_OFFERS"])
        return trading.betting.list_market_book(market_ids=market_ids, price_projection=price_projection)

    def get_lay_odds_for_catalogues(self, catalogues):
        market_ids = [c["market_id"] for c in catalogues]
        books = []
        for i in range(0, len(market_ids), 40):
            books.extend(self.list_market_books(market_ids[i:i+40]))
        by_id = {b.market_id: b for b in books}
        out = []
        for c in catalogues:
            book = by_id.get(c["market_id"])
            if not book: continue
            runner_meta = {r["selection_id"]: r for r in c["runners"]}
            for runner in book.runners:
                meta = runner_meta.get(runner.selection_id)
                if not meta: continue
                available = runner.ex.available_to_lay if runner.ex else []
                if not available: continue
                best = available[0]
                out.append({"market_id": c["market_id"], "event_id": c["event_id"], "event_name": c["event_name"], "start_time": c["start_time"], "market": c["market"], "selection": meta["selection"], "lay_price": float(best.price), "lay_size": float(best.size or 0)})
        return out
