from services.scanner import QuoteScanner


class EmptyOdds:
    api_calls = 3

    def parse_events(self):
        return []


class FailingBetfair:
    def list_market_catalogue(self):
        raise AssertionError("Betfair should not be called without OddsPapi events")


def test_refresh_skips_betfair_when_oddspapi_has_no_events():
    from database.init_db import init_db

    init_db()
    scanner = QuoteScanner()
    scanner.odds = EmptyOdds()
    scanner.betfair = FailingBetfair()

    result = scanner.refresh()

    assert result["status"] == "ok"
    assert result["events"] == 0
    assert result["betfair_markets"] == 0
