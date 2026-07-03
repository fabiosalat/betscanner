from database.db import get_connection


def test_health_and_db_startup():
    import app as app_module
    response = app_module.app.test_client().get("/health")

    assert response.status_code == 200
    assert response.get_json() == {"status": "ok"}
    with get_connection() as conn:
        assert conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='events'").fetchone()


def test_refresh_falls_back_when_credentials_are_missing(monkeypatch):
    import app as app_module
    monkeypatch.setattr(app_module, "missing_api_credentials", lambda: ["ODDSPAPI_KEY"])

    response = app_module.app.test_client().get("/refresh?json=1")

    assert response.status_code == 200
    assert response.get_json()["status"] == "missing_credentials"


def test_export_xlsx_smoke():
    import app as app_module

    response = app_module.app.test_client().get("/export/surebet")

    assert response.status_code == 200
    assert response.headers["Content-Type"].startswith("application/vnd.openxmlformats")
