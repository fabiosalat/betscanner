def test_missing_api_credentials_accepts_betfair_ssoid(monkeypatch):
    import config

    monkeypatch.setattr(config, "ODDSPAPI_KEY", "odds")
    monkeypatch.setattr(config, "BETFAIR_APP_KEY", "app")
    monkeypatch.setattr(config, "BETFAIR_SSOID", "sso")
    monkeypatch.setattr(config, "BETFAIR_USERNAME", "")
    monkeypatch.setattr(config, "BETFAIR_PASSWORD", "")
    monkeypatch.setattr(config, "BETFAIR_CERT", "")
    monkeypatch.setattr(config, "BETFAIR_KEY", "")

    assert config.missing_api_credentials() == []


def test_betfair_login_uses_ssoid(monkeypatch):
    import services.betfair_service as betfair_service

    monkeypatch.setattr(betfair_service, "BETFAIR_APP_KEY", "app")
    monkeypatch.setattr(betfair_service, "BETFAIR_SSOID", " token ")
    monkeypatch.setattr(betfair_service, "BETFAIR_USERNAME", "")
    monkeypatch.setattr(betfair_service, "BETFAIR_PASSWORD", "")
    monkeypatch.setattr(betfair_service, "BETFAIR_LOCALE", "italy")

    created = {}

    class Client:
        def __init__(self, username, password, app_key, certs=None, cert_files=None, locale=None):
            created["args"] = (username, password, app_key, certs, cert_files, locale)
            self.session_token = None

        def set_session_token(self, token):
            self.session_token = token

    monkeypatch.setattr(betfair_service.betfairlightweight, "APIClient", Client)

    trading = betfair_service.BetfairService().login()

    assert created["args"] == ("", "", "app", None, None, "italy")
    assert trading.session_token == "token"


def test_betfair_certificate_login_uses_italy_locale_and_cert_files(monkeypatch, tmp_path):
    import services.betfair_service as betfair_service

    cert = tmp_path / "client-2048.crt"
    key = tmp_path / "client-2048.key"
    cert.write_text("cert", encoding="utf-8")
    key.write_text("key", encoding="utf-8")
    monkeypatch.setattr(betfair_service, "BETFAIR_APP_KEY", "app")
    monkeypatch.setattr(betfair_service, "BETFAIR_SSOID", "")
    monkeypatch.setattr(betfair_service, "BETFAIR_USERNAME", "user")
    monkeypatch.setattr(betfair_service, "BETFAIR_PASSWORD", "pass")
    monkeypatch.setattr(betfair_service, "BETFAIR_CERT_FILE", str(cert))
    monkeypatch.setattr(betfair_service, "BETFAIR_KEY_FILE", str(key))
    monkeypatch.setattr(betfair_service, "BETFAIR_LOCALE", "italy")
    created = {}

    class Client:
        def __init__(self, username, password, app_key, certs=None, cert_files=None, locale=None):
            created["args"] = (username, password, app_key, certs, cert_files, locale)

        def login(self):
            created["login"] = True

    monkeypatch.setattr(betfair_service.betfairlightweight, "APIClient", Client)

    betfair_service.BetfairService().login()

    assert created["args"] == ("user", "pass", "app", None, (str(cert), str(key)), "italy")
    assert created["login"] is True


def test_call_betting_api_uses_json_rpc_headers(monkeypatch):
    import services.betfair_service as betfair_service

    service = betfair_service.BetfairService()
    service.trading = type("Trading", (), {"session_token": "session"})()
    captured = {}

    class Response:
        status_code = 200
        text = ""

        def json(self):
            return {"result": [{"eventType": {"id": "1"}}]}

    def fake_post(url, json, headers, timeout):
        captured.update(url=url, json=json, headers=headers, timeout=timeout)
        return Response()

    monkeypatch.setattr(betfair_service, "BETFAIR_APP_KEY", "app")
    monkeypatch.setattr(betfair_service, "BETFAIR_BETTING_API_URL", "https://api.betfair.com/exchange/betting/json-rpc/v1")
    monkeypatch.setattr(betfair_service.requests, "post", fake_post)

    assert service.call_betting_api("listEventTypes", {"filter": {}}) == [{"eventType": {"id": "1"}}]
    assert captured["url"] == "https://api.betfair.com/exchange/betting/json-rpc/v1"
    assert captured["headers"]["X-Application"] == "app"
    assert captured["headers"]["X-Authentication"] == "session"
    assert captured["json"]["method"] == "SportsAPING/v1.0/listEventTypes"


def test_call_betting_api_reports_http_body(monkeypatch):
    import pytest
    import services.betfair_service as betfair_service

    service = betfair_service.BetfairService()
    service.trading = type("Trading", (), {"session_token": "session"})()

    class Response:
        status_code = 403
        text = "forbidden body"

    monkeypatch.setattr(betfair_service.requests, "post", lambda *args, **kwargs: Response())

    with pytest.raises(RuntimeError, match="forbidden body"):
        service.call_betting_api("listEventTypes", {"filter": {}})


def test_call_betting_api_reports_cloudflare_block(monkeypatch):
    import pytest
    import services.betfair_service as betfair_service

    service = betfair_service.BetfairService()
    service.trading = type("Trading", (), {"session_token": "session"})()

    class Response:
        status_code = 403
        text = "<title>Attention Required! | Cloudflare</title>"

    monkeypatch.setattr(betfair_service.requests, "post", lambda *args, **kwargs: Response())

    with pytest.raises(RuntimeError, match="Cloudflare"):
        service.call_betting_api("listEventTypes", {"filter": {}})


def test_parse_market_catalogues_supports_lightweight_dicts():
    import services.betfair_service as betfair_service

    rows = betfair_service.BetfairService().parse_market_catalogues([{
        "marketId": "1.23",
        "marketStartTime": "2026-07-03T18:30:00.000Z",
        "description": {"marketType": "MATCH_ODDS", "betDelayModels": ["PASSIVE"]},
        "event": {"id": "100", "name": "Team A v Team B"},
        "runners": [
            {"selectionId": 1, "runnerName": "Team A"},
            {"selectionId": 2, "runnerName": "Team B"},
            {"selectionId": 3, "runnerName": "The Draw"},
        ],
    }])

    assert rows == [{
        "market_id": "1.23",
        "market": "MATCH_ODDS",
        "event_name": "Team A v Team B",
        "event_id": "100",
        "start_time": "2026-07-03T18:30:00.000Z",
        "runners": [
            {"selection_id": 1, "runner_name": "Team A", "selection": "HOME"},
            {"selection_id": 2, "runner_name": "Team B", "selection": "AWAY"},
            {"selection_id": 3, "runner_name": "The Draw", "selection": "DRAW"},
        ],
    }]


def test_get_lay_odds_supports_lightweight_dicts(monkeypatch):
    import services.betfair_service as betfair_service

    service = betfair_service.BetfairService()
    monkeypatch.setattr(service, "list_market_books", lambda market_ids: [{
        "marketId": "1.23",
        "runners": [{"selectionId": 1, "ex": {"availableToLay": [{"price": 2.04, "size": 10}]}}],
    }])

    rows = service.get_lay_odds_for_catalogues([{
        "market_id": "1.23",
        "event_id": "100",
        "event_name": "Team A v Team B",
        "start_time": "2026-07-03T18:30:00.000Z",
        "market": "MATCH_ODDS",
        "runners": [{"selection_id": 1, "selection": "HOME"}],
    }])

    assert rows == [{
        "market_id": "1.23",
        "event_id": "100",
        "event_name": "Team A v Team B",
        "start_time": "2026-07-03T18:30:00.000Z",
        "market": "MATCH_ODDS",
        "selection": "HOME",
        "lay_price": 2.04,
        "lay_size": 10.0,
    }]
