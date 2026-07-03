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

    created = {}

    class Client:
        def __init__(self, username, password, app_key, certs=None):
            created["args"] = (username, password, app_key, certs)
            self.session_token = None

        def set_session_token(self, token):
            self.session_token = token

    monkeypatch.setattr(betfair_service.betfairlightweight, "APIClient", Client)

    trading = betfair_service.BetfairService().login()

    assert created["args"] == ("", "", "app", None)
    assert trading.session_token == "token"
