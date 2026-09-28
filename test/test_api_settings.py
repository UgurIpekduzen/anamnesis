from datetime import datetime, timezone

from starlette.testclient import TestClient

import api.main as api_main
from api.routers import settings as settings_router

OWNER = "test@example.com"


def test_settings_require_authentication():
    # No dependency override here: the real token check must run.
    client = TestClient(api_main.app)
    assert client.get("/usage").status_code == 401


def test_usage_reports_the_users_own_threshold(monkeypatch, signed_in_owner):
    client = TestClient(api_main.app)
    monkeypatch.setattr(settings_router, "get_today_count", lambda owner_uid: 3)
    monkeypatch.setattr(
        settings_router, "get_settings", lambda: {"history_turns": 20, "daily_message_warning_threshold": 7}
    )

    body = client.get("/usage").json()

    assert (body["count"], body["threshold"]) == (3, 7)


def test_usage_reports_the_hard_limit_and_when_it_resets(monkeypatch, signed_in_owner):
    client = TestClient(api_main.app)
    monkeypatch.setattr(settings_router, "get_today_count", lambda owner_uid: 3)
    monkeypatch.setattr(
        settings_router, "get_settings", lambda: {"history_turns": 20, "daily_message_warning_threshold": 7}
    )
    monkeypatch.setattr(settings_router, "DAILY_MESSAGE_HARD_LIMIT", 150)

    body = client.get("/usage").json()

    assert body["limit"] == 150
    reset = datetime.fromisoformat(body["resets_at"])
    assert reset > datetime.now(timezone.utc)
    assert (reset.hour, reset.minute, reset.second) == (0, 0, 0)
