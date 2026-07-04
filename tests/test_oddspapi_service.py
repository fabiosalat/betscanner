from datetime import datetime
import pytest
import requests
from services.oddspapi_service import BOOKMAKER_SLUGS, OddsPapiService, normalize_bookmaker


def test_parse_events_ignores_unknown_response_shape(monkeypatch):
    service = OddsPapiService(api_key="x")
    monkeypatch.setattr(service, "fetch_raw_events", lambda: {"unexpected": "shape"})

    assert service.parse_events() == []


def test_fetch_raw_events_uses_v4_fixtures(monkeypatch):
    service = OddsPapiService(api_key="x")
    captured = {}

    def fake_get(path, params):
        captured["path"] = path
        captured["params"] = params
        return [{"fixtureId": "id1", "tournamentName": "FIFA World Cup"}]

    monkeypatch.setattr(service, "_get", fake_get)

    assert service.fetch_raw_events() == [{"fixtureId": "id1", "tournamentName": "FIFA World Cup"}]
    assert captured["path"] == "/v4/fixtures"
    assert captured["params"]["sportId"] == 10
    assert captured["params"]["statusId"] == 0
    assert captured["params"]["hasOdds"] == "true"
    assert "bookmakers" not in captured["params"]
    from_dt = datetime.fromisoformat(captured["params"]["from"].replace("Z", "+00:00"))
    to_dt = datetime.fromisoformat(captured["params"]["to"].replace("Z", "+00:00"))
    assert (to_dt - from_dt).total_seconds() < 48 * 60 * 60


def test_fetch_raw_events_keeps_only_allowed_tournaments(monkeypatch):
    service = OddsPapiService(api_key="x")
    monkeypatch.setattr(service, "_get", lambda path, params: [
        {"fixtureId": "world-cup", "tournamentName": "FIFA World Cup"},
        {"fixtureId": "serie-a", "tournamentName": "Serie A"},
        {"fixtureId": "wimbledon", "tournamentName": "Wimbledon"},
    ])

    assert [ev["fixtureId"] for ev in service.fetch_raw_events()] == ["world-cup", "wimbledon"]


def test_get_reports_unauthorized_oddspapi_key(monkeypatch):
    service = OddsPapiService(api_key=" x ")
    captured = {}

    class Response:
        status_code = 401

        def raise_for_status(self):
            raise requests.HTTPError("401")

    def fake_get(*args, **kwargs):
        captured["params"] = kwargs["params"]
        return Response()

    monkeypatch.setattr(service.session, "get", fake_get)

    with pytest.raises(RuntimeError, match="ODDSPAPI_KEY non valida"):
        service._get("/v4/fixtures", {})
    assert captured["params"]["apiKey"] == "x"


def test_get_reports_rate_limit_without_retry(monkeypatch):
    service = OddsPapiService(api_key="x")
    calls = []

    class Response:
        status_code = 429

        def raise_for_status(self):
            raise requests.HTTPError("429")

    monkeypatch.setattr(service.session, "get", lambda *args, **kwargs: calls.append(kwargs) or Response())

    with pytest.raises(RuntimeError, match="rate limit"):
        service._get("/v4/fixtures", {})
    assert len(calls) == 1


def test_get_reports_bad_request_without_leaking_api_key(monkeypatch):
    service = OddsPapiService(api_key="secret-key")

    class Response:
        status_code = 400
        text = "bad filter"

        def json(self):
            return {"message": "bad filter"}

        def raise_for_status(self):
            raise requests.HTTPError("400")

    monkeypatch.setattr(service.session, "get", lambda *args, **kwargs: Response())

    with pytest.raises(RuntimeError) as exc:
        service._get("/v4/fixtures", {})

    assert "bad filter" in str(exc.value)
    assert "/v4/fixtures" in str(exc.value)
    assert "secret-key" not in str(exc.value)
    assert "apiKey" not in str(exc.value)


def test_get_waits_between_oddspapi_calls(monkeypatch):
    service = OddsPapiService(api_key="x")
    sleeps = []
    now = [100.0]

    class Response:
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            return []

    def fake_sleep(seconds):
        sleeps.append(seconds)
        now[0] += seconds

    monkeypatch.setattr("services.oddspapi_service.ODDSPAPI_REQUEST_COOLDOWN_SECONDS", 2.1)
    monkeypatch.setattr("services.oddspapi_service.monotonic", lambda: now[0])
    monkeypatch.setattr("services.oddspapi_service.sleep", fake_sleep)
    monkeypatch.setattr(service.session, "get", lambda *args, **kwargs: Response())

    service._get("/v4/fixtures", {})
    now[0] += 1.0
    service._get("/v4/fixtures", {})

    assert sleeps == [pytest.approx(1.1)]


def test_static_oddspapi_endpoints_are_cached(monkeypatch):
    service = OddsPapiService(api_key="x")
    calls = []

    class Response:
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            return [{"marketId": 101, "marketName": "Full Time Result"}]

    monkeypatch.setattr(service.session, "get", lambda *args, **kwargs: calls.append(kwargs) or Response())

    assert service._get("/v4/markets", {"language": "en"}) == [{"marketId": 101, "marketName": "Full Time Result"}]
    assert service._get("/v4/markets", {"language": "en"}) == [{"marketId": 101, "marketName": "Full Time Result"}]
    assert len(calls) == 1


def test_fetch_odds_by_tournaments_batches_unique_tournaments(monkeypatch):
    service = OddsPapiService(api_key="x")
    batches = []
    monkeypatch.setattr("services.oddspapi_service.ODDS_BATCH_SIZE", 2)
    monkeypatch.setattr("services.oddspapi_service.BOOKMAKERS", ["Sisal IT", "Bet365 IT"])

    def fake_fetch_tournament_odds(tournament_ids, bookmaker):
        batches.append((tournament_ids, bookmaker))
        return [{
            "fixtureId": f"id{tournament_id}",
            "tournamentId": tournament_id,
            "bookmakerOdds": {bookmaker: {"markets": {}}},
        } for tournament_id in tournament_ids]

    monkeypatch.setattr(service, "fetch_tournament_odds", fake_fetch_tournament_odds)

    rows = service.fetch_odds_by_tournaments([
        {"fixtureId": "a", "tournamentId": 2, "hasOdds": True},
        {"fixtureId": "b", "tournamentId": 1, "hasOdds": True},
        {"fixtureId": "c", "tournamentId": 2, "hasOdds": True},
        {"fixtureId": "d", "tournamentId": 3, "hasOdds": False},
        {"fixtureId": "e", "tournamentId": 4, "hasOdds": True},
    ])

    assert batches == [([1, 2], "sisal.it"), ([4], "sisal.it"), ([1, 2], "bet365"), ([4], "bet365")]
    assert rows["id1"]["tournamentId"] == 1
    assert rows["id4"]["tournamentId"] == 4
    assert rows["id1"]["bookmakerOdds"] == {"sisal.it": {"markets": {}}, "bet365": {"markets": {}}}


def test_parse_events_fetches_v4_odds_for_fixtures_with_odds(monkeypatch):
    service = OddsPapiService(api_key="x")
    monkeypatch.setattr(service, "fetch_raw_events", lambda: [{
        "fixtureId": "id1",
        "participant1Name": "Inter Milan",
        "participant2Name": "AC Milan",
        "tournamentName": "Serie A",
        "hasOdds": True,
    }])
    monkeypatch.setattr(service, "fetch_odds_by_tournaments", lambda events: {})
    monkeypatch.setattr(service, "fetch_fixture_odds", lambda fixture_id: {
        "bookmakerOdds": {
            "bet365": {
                "suspended": False,
                "markets": {
                    "101": {
                        "marketActive": True,
                        "outcomes": {
                            "101": {"players": {"0": {"active": True, "price": 2.1}}},
                        },
                    },
                },
            },
        },
    })
    service._markets = {"101": {"marketId": 101, "marketName": "Full Time Result", "period": "fulltime", "outcomes": [{"outcomeId": 101, "outcomeName": "1"}]}}

    assert service.parse_events()[0]["odds"] == [{"bookmaker": "Bet365 IT", "market": "MATCH_ODDS", "selection": "HOME", "odd": 2.1}]


def test_parse_events_supports_v4_fixture_shape(monkeypatch):
    service = OddsPapiService(api_key="x")
    monkeypatch.setattr(service, "fetch_raw_events", lambda: [{
        "fixtureId": "id1000001761301153",
        "participant1Name": "Liverpool FC",
        "participant2Name": "Manchester United",
        "startTime": "2026-04-13T19:00:00.000Z",
        "tournamentName": "Premier League",
    }])
    monkeypatch.setattr(service, "fetch_odds_by_tournaments", lambda events: {})

    assert service.parse_events() == [{
        "odds_event_id": "id1000001761301153",
        "league": "Premier League",
        "home_team": "Liverpool FC",
        "away_team": "Manchester United",
        "start_time": "2026-04-13T19:00:00.000Z",
        "normalized_home": "liverpool",
        "normalized_away": "manchester united",
        "odds": [],
    }]


def test_parse_odds_ignores_unknown_nested_shapes():
    service = OddsPapiService(api_key="x")

    assert service.parse_odds({"id": "1", "bookmakers": "bad"}) == []


def test_parse_odds_supports_v4_bookmaker_odds():
    service = OddsPapiService(api_key="x")
    service._markets = {
        "104": {
            "marketId": 104,
            "marketName": "Both Teams To Score",
            "period": "fulltime",
            "outcomes": [{"outcomeId": 104, "outcomeName": "Yes"}, {"outcomeId": 105, "outcomeName": "No"}],
        }
    }

    rows = service.parse_odds({
        "bookmakerOdds": {
            "sisal": {
                "suspended": False,
                "markets": {
                    "104": {
                        "marketActive": True,
                        "outcomes": {
                            "104": {"players": {"0": {"active": True, "price": 1.8}}},
                            "105": {"players": {"0": {"active": True, "price": 1.95}}},
                        },
                    },
                },
            }
        }
    })

    assert rows == [
        {"bookmaker": "Sisal IT", "market": "BTTS", "selection": "YES", "odd": 1.8},
        {"bookmaker": "Sisal IT", "market": "BTTS", "selection": "NO", "odd": 1.95},
    ]


def test_normalize_bookmaker_aliases():
    assert normalize_bookmaker("bet365") == "Bet365 IT"
    assert normalize_bookmaker("planetwin365") == "Planetwin365 IT"
    assert normalize_bookmaker("snai_it") == "Snai IT"
    assert normalize_bookmaker("sisal.it") == "Sisal IT"


def test_italian_bookmaker_slugs_match_oddspapi():
    assert BOOKMAKER_SLUGS == {
        "Sisal IT": "sisal.it",
        "Snai IT": "snai.it",
        "Eurobet IT": "eurobet.it",
        "Planetwin365 IT": "planetwin365.it",
        "Betflag IT": "betflag.it",
        "Bet365 IT": "bet365",
        "EPLAY24 IT": "eplay24.it",
    }
