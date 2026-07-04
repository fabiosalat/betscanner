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


def test_refresh_skips_betfair_when_oddspapi_has_no_events():
    from database.init_db import init_db
    from database.repository import Repository

    init_db()
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

    init_db()
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
