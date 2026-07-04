from datetime import datetime
import pytest
import requests
from services.oddspapi_service import BOOKMAKER_SLUGS, OddsPapiService, allowed_bookmaker_slugs, normalize_bookmaker, normalize_market, normalize_selection


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


def test_market_by_id_uses_db_catalog_without_calling_markets_api(monkeypatch):
    import services.oddspapi_service as oddspapi_service

    class Repo:
        def get_oddspapi_markets(self):
            return [{"marketId": 1010, "marketName": "Over Under Full Time"}]

        def save_oddspapi_markets(self, markets):
            raise AssertionError("catalog should already be cached")

    service = OddsPapiService(api_key="x")
    monkeypatch.setattr(oddspapi_service, "Repository", Repo)
    monkeypatch.setattr(service, "_get", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("/v4/markets should not be called")))

    assert service.market_by_id("1010") == {"marketId": 1010, "marketName": "Over Under Full Time"}


def test_fetch_odds_by_tournaments_batches_unique_tournaments(monkeypatch):
    batches = []
    monkeypatch.setattr("services.oddspapi_service.ODDS_BATCH_SIZE", 2)
    service = OddsPapiService(api_key="x", bookmakers=["Sisal IT", "Bet365 IT"])

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


def test_allowed_bookmaker_slugs_uses_oddspapi_maximum_by_default(monkeypatch):
    monkeypatch.setattr("services.oddspapi_service.ODDSPAPI_MAX_BOOKMAKERS", 5)

    assert allowed_bookmaker_slugs() == ["sisal.it", "snai.it", "eurobet.it", "planetwin365.it", "betflag.it"]


def test_allowed_bookmaker_slugs_respects_explicit_limit(monkeypatch):
    monkeypatch.setattr("services.oddspapi_service.ODDSPAPI_MAX_BOOKMAKERS", 2)

    assert allowed_bookmaker_slugs() == ["sisal.it", "snai.it"]


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

    assert service.parse_events()[0]["odds"] == [{"bookmaker": "Bet365 IT", "market": "MATCH_ODDS", "selection": "HOME", "odd": 2.1, "oddspapi_market_id": "101", "oddspapi_outcome_id": "101", "market_name": "Full Time Result", "selection_name": "1"}]


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
        {"bookmaker": "Sisal IT", "market": "BTTS", "selection": "YES", "odd": 1.8, "oddspapi_market_id": "104", "oddspapi_outcome_id": "104", "market_name": "Both Teams To Score", "selection_name": "Yes"},
        {"bookmaker": "Sisal IT", "market": "BTTS", "selection": "NO", "odd": 1.95, "oddspapi_market_id": "104", "oddspapi_outcome_id": "105", "market_name": "Both Teams To Score", "selection_name": "No"},
    ]


def test_normalize_market_maps_only_truthful_equivalents():
    assert normalize_market("Full Time Result", period="fulltime", market_type="1x2") == "MATCH_ODDS"
    assert normalize_market("Second Half Result", period="p2", market_type="1x2") == ""
    assert normalize_market("Draw No Bet Full Time", period="fulltime", market_type="drawnobet") == "DRAW_NO_BET"
    assert normalize_market("Correct Score Full Time", period="fulltime", market_type="correctscore") == "CORRECT_SCORE"
    assert normalize_market("Correct Score First Half", period="p1", market_type="correctscore") == "CORRECT_SCORE_HT"
    assert normalize_market("Draw No Bet First Half", period="p1", market_type="drawnobet") == ""
    assert normalize_market("Over Under Second Half", line=2.5, period="p2", market_type="totals") == ""
    assert normalize_market("Over Under Full Time", line=8.5, period="fulltime", market_type="totals") == "OVER_UNDER_85"
    assert normalize_market("Over Under First Half", line=2.5, period="p1", market_type="totals") == "OVER_UNDER_HT_25"
    assert normalize_market("First Goal Full Time", period="fulltime", market_type="firstgoal") == ""
    assert normalize_market("Over Under Team 2", line=2.5, period="fulltime", market_type="teamtotals-team2") == ""
    assert normalize_market("Winner (incl. overtime)", line=0, period="result", market_type="moneyline") == ""
    assert normalize_selection("2X") == "X2"


def test_parse_odds_keeps_main_total_goals_without_team_total_collision():
    service = OddsPapiService(api_key="x")
    service._markets = {
        "1010": {
            "marketId": 1010,
            "marketName": "Over Under Full Time",
            "marketType": "totals",
            "handicap": 2.5,
            "period": "fulltime",
            "outcomes": [{"outcomeId": 1010, "outcomeName": "Over"}, {"outcomeId": 1011, "outcomeName": "Under"}],
        },
        "10244": {
            "marketId": 10244,
            "marketName": "Over Under Team 2",
            "marketType": "teamtotals-team2",
            "handicap": 2.5,
            "period": "fulltime",
            "outcomes": [{"outcomeId": 10244, "outcomeName": "Over"}, {"outcomeId": 10245, "outcomeName": "Under"}],
        },
    }

    rows = service.parse_odds({
        "bookmakerOdds": {
            "sisal.it": {
                "suspended": False,
                "markets": {
                    "1010": {
                        "marketActive": True,
                        "outcomes": {
                            "1011": {"players": {"0": {"active": True, "price": 2.0}}},
                            "1010": {"players": {"0": {"active": True, "price": 1.72}}},
                        },
                    },
                    "10244": {
                        "marketActive": True,
                        "outcomes": {
                            "10245": {"players": {"0": {"active": True, "price": 1.05}}},
                            "10244": {"players": {"0": {"active": True, "price": 7.5}}},
                        },
                    },
                },
            }
        }
    })

    assert rows == [
        {"bookmaker": "Sisal IT", "market": "OVER_UNDER_25", "selection": "UNDER", "odd": 2.0, "oddspapi_market_id": "1010", "oddspapi_outcome_id": "1011", "market_name": "Over Under Full Time", "selection_name": "Under"},
        {"bookmaker": "Sisal IT", "market": "OVER_UNDER_25", "selection": "OVER", "odd": 1.72, "oddspapi_market_id": "1010", "oddspapi_outcome_id": "1010", "market_name": "Over Under Full Time", "selection_name": "Over"},
    ]


def test_parse_odds_requires_outcome_id_from_market_metadata():
    service = OddsPapiService(api_key="x")
    service._markets = {
        "1010": {
            "marketId": 1010,
            "marketName": "Over Under Full Time",
            "marketType": "totals",
            "handicap": 2.5,
            "period": "fulltime",
            "outcomes": [{"outcomeId": 1010, "outcomeName": "Over"}],
        },
    }

    rows = service.parse_odds({
        "bookmakerOdds": {
            "sisal.it": {
                "suspended": False,
                "markets": {
                    "1010": {
                        "marketActive": True,
                        "outcomes": {
                            "9999": {"players": {"0": {"active": True, "price": 9.9, "bookmakerOutcomeId": "Over"}}},
                        },
                    },
                },
            }
        }
    })

    assert rows == []


def test_parse_odds_maps_correct_score_and_ignores_unsupported_markets():
    service = OddsPapiService(api_key="x")
    service._markets = {
        "10336": {
            "marketId": 10336,
            "marketName": "Correct Score Full Time",
            "marketType": "correctscore",
            "period": "fulltime",
            "outcomes": [{"outcomeId": 1, "outcomeName": "0:0"}],
        },
        "10216": {
            "marketId": 10216,
            "marketName": "First Goal Full Time",
            "marketType": "firstgoal",
            "period": "fulltime",
            "outcomes": [{"outcomeId": 2, "outcomeName": "1"}],
        },
    }

    rows = service.parse_odds({
        "bookmakerOdds": {
            "bet365": {
                "suspended": False,
                "markets": {
                    "10336": {"marketActive": True, "outcomes": {"1": {"players": {"0": {"active": True, "price": 7.5}}}}},
                    "10216": {"marketActive": True, "outcomes": {"2": {"players": {"0": {"active": True, "price": 3.1}}}}},
                },
            }
        }
    })

    assert rows == [{"bookmaker": "Bet365 IT", "market": "CORRECT_SCORE", "selection": "0:0", "odd": 7.5, "oddspapi_market_id": "10336", "oddspapi_outcome_id": "1", "market_name": "Correct Score Full Time", "selection_name": "0:0"}]


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
