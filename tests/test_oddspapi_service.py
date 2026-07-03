from services.oddspapi_service import OddsPapiService, normalize_bookmaker


def test_parse_events_ignores_unknown_response_shape(monkeypatch):
    service = OddsPapiService(api_key="x")
    monkeypatch.setattr(service, "fetch_raw_events", lambda: {"unexpected": "shape"})

    assert service.parse_events() == []


def test_parse_odds_ignores_unknown_nested_shapes():
    service = OddsPapiService(api_key="x")

    assert service.parse_odds({"id": "1", "bookmakers": "bad"}) == []


def test_normalize_bookmaker_aliases():
    assert normalize_bookmaker("bet365") == "Bet365 IT"
    assert normalize_bookmaker("planetwin365") == "Planetwin365 IT"
    assert normalize_bookmaker("snai_it") == "Snai IT"
