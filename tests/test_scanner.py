from services.scanner import QuoteScanner


class EmptyOdds:
    api_calls = 3

    def parse_events(self):
        return []


class FailingBetfair:
    def list_market_catalogue(self):
        raise AssertionError("Betfair should not be called without OddsPapi events")


class RateLimitedOdds:
    api_calls = 1

    def parse_events(self):
        raise RuntimeError("OddsPapi rate limit: troppe richieste ravvicinate, attendi il cooldown prima di riprovare")


class OneEventOdds:
    api_calls = 2

    def parse_events(self):
        return [{
            "odds_event_id": "odds-1",
            "league": "FIFA World Cup",
            "home_team": "Team A",
            "away_team": "Team B",
            "start_time": "2026-07-04T12:00:00Z",
            "normalized_home": "team a",
            "normalized_away": "team b",
            "odds": [{"bookmaker": "Sisal IT", "market": "MATCH_ODDS", "selection": "HOME", "odd": 2.1}],
        }]


class ForbiddenBetfair:
    api_calls = 1

    def list_market_catalogue(self):
        raise RuntimeError("Status code error: 403")


class UnusedOdds:
    def parse_events(self):
        raise AssertionError("OddsPapi should be paused in Betfair-only mode")


class WorkingBetfair:
    api_calls = 2

    def list_market_catalogue(self):
        return [{"market_id": "1.1"}]

    def get_lay_odds_for_catalogues(self, catalogues):
        return [{"market_id": "1.1"}]


def test_refresh_skips_betfair_when_oddspapi_has_no_events():
    from database.init_db import init_db
    from database.repository import Repository
    import services.scanner as scanner_module

    init_db()
    scanner_module.BETFAIR_ONLY_MODE = False
    Repository().set_cache("oddspapi_rate_limited_until", 0)
    scanner = QuoteScanner()
    scanner.odds = EmptyOdds()
    scanner.betfair = FailingBetfair()

    result = scanner.refresh()

    assert result["status"] == "ok"
    assert result["events"] == 0
    assert result["betfair_markets"] == 0


def test_refresh_caches_oddspapi_rate_limit():
    from database.init_db import init_db
    from database.repository import Repository
    import services.scanner as scanner_module

    init_db()
    scanner_module.BETFAIR_ONLY_MODE = False
    Repository().set_cache("oddspapi_rate_limited_until", 0)
    scanner = QuoteScanner()
    scanner.odds = RateLimitedOdds()
    scanner.betfair = FailingBetfair()

    first = scanner.refresh()
    second = scanner.refresh()

    assert first["status"] == "error"
    assert first["api_calls"] == 1
    assert second["status"] == "rate_limited"
    assert second["api_calls"] == 0


def test_refresh_keeps_oddspapi_data_when_betfair_fails():
    from database.init_db import init_db
    from database.repository import Repository
    import services.scanner as scanner_module

    init_db()
    scanner_module.BETFAIR_ONLY_MODE = False
    Repository().set_cache("oddspapi_rate_limited_until", 0)
    scanner = QuoteScanner()
    scanner.odds = OneEventOdds()
    scanner.betfair = ForbiddenBetfair()

    result = scanner.refresh()

    assert result["status"] == "warning"
    assert result["events"] == 1
    assert result["bookmaker_odds"] == 1
    assert result["betfair_markets"] == 0
    assert "Betfair non disponibile" in result["message"]


def test_refresh_can_run_betfair_only(monkeypatch):
    from database.init_db import init_db
    import services.scanner as scanner_module

    init_db()
    monkeypatch.setattr(scanner_module, "BETFAIR_ONLY_MODE", True)
    scanner = QuoteScanner()
    scanner.odds = UnusedOdds()
    scanner.betfair = WorkingBetfair()

    result = scanner.refresh()

    assert result["status"] == "ok"
    assert result["events"] == 0
    assert result["betfair_markets"] == 1
    assert result["betfair_lays"] == 1
    assert result["api_calls"] == 2
