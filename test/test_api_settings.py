from datetime import datetime, timezone

import pytest
from starlette.testclient import TestClient

import api.main as api_main
from api.routers import settings as settings_router
from src.accounts.settings import BOUNDS, DEFAULTS

OWNER = "test@example.com"
CURRENT = {"history_turns": 20, "daily_message_warning_threshold": 100}


@pytest.fixture
def api(monkeypatch, signed_in_owner):
    saved = []

    def fake_save(owner_uid, settings):
        saved.append((owner_uid, settings))
        return settings

    monkeypatch.setattr(settings_router, "get_settings", lambda owner_uid: dict(CURRENT))
    monkeypatch.setattr(settings_router, "save_settings", fake_save)
    yield TestClient(api_main.app), saved


def test_get_also_returns_the_defaults_so_the_ui_knows_what_reset_means(api):
    client, _ = api
    assert client.get("/settings").json()["defaults"] == DEFAULTS


def test_delete_resets_the_authenticated_users_settings(api, monkeypatch):
    client, _ = api
    resets = []
    monkeypatch.setattr(
        settings_router, "reset_settings", lambda owner_uid: resets.append(owner_uid) or dict(DEFAULTS)
    )

    response = client.delete("/settings")

    assert response.status_code == 200
    assert response.json()["history_turns"] == DEFAULTS["history_turns"]
    assert resets == [OWNER]


def test_get_returns_the_settings_and_their_limits(api):
    client, _ = api
    body = client.get("/settings").json()

    assert body["history_turns"] == 20
    assert body["daily_message_warning_threshold"] == 100
    assert body["limits"]["history_turns"] == {
        "min": BOUNDS["history_turns"][0],
        "max": BOUNDS["history_turns"][1],
    }


def test_put_saves_for_the_authenticated_user(api):
    client, saved = api
    payload = {"history_turns": 5, "daily_message_warning_threshold": 40}

    response = client.put("/settings", json=payload)

    assert response.status_code == 200
    assert response.json()["history_turns"] == 5
    assert saved == [(OWNER, payload)]


@pytest.mark.parametrize(
    "payload",
    [
        {"history_turns": 0, "daily_message_warning_threshold": 40},
        {"history_turns": BOUNDS["history_turns"][1] + 1, "daily_message_warning_threshold": 40},
        {"history_turns": 5, "daily_message_warning_threshold": 0},
        {"history_turns": 5, "daily_message_warning_threshold": BOUNDS["daily_message_warning_threshold"][1] + 1},
        {"history_turns": "5", "daily_message_warning_threshold": 40},
        {"history_turns": True, "daily_message_warning_threshold": 40},
        {"history_turns": 5},
        {"history_turns": 5, "daily_message_warning_threshold": 40, "owner_uid": "someone-else@example.com"},
    ],
)
def test_put_rejects_invalid_payloads_and_saves_nothing(api, payload):
    client, saved = api
    assert client.put("/settings", json=payload).status_code == 422
    assert saved == []


def test_settings_require_authentication():
    # No dependency override here: the real token check must run.
    client = TestClient(api_main.app)
    assert client.get("/settings").status_code == 401
    assert client.put("/settings", json={}).status_code == 401
    assert client.delete("/settings").status_code == 401


def test_usage_reports_the_users_own_threshold(api, monkeypatch):
    client, _ = api
    monkeypatch.setattr(settings_router, "get_today_count", lambda owner_uid: 3)
    monkeypatch.setattr(
        settings_router, "get_settings", lambda owner_uid: {"history_turns": 20, "daily_message_warning_threshold": 7}
    )

    body = client.get("/usage").json()

    assert (body["count"], body["threshold"]) == (3, 7)


def test_usage_reports_the_hard_limit_and_when_it_resets(api, monkeypatch):
    client, _ = api
    monkeypatch.setattr(settings_router, "get_today_count", lambda owner_uid: 3)
    monkeypatch.setattr(
        settings_router, "get_settings", lambda owner_uid: {"history_turns": 20, "daily_message_warning_threshold": 7}
    )
    monkeypatch.setattr(settings_router, "DAILY_MESSAGE_HARD_LIMIT", 150)

    body = client.get("/usage").json()

    assert body["limit"] == 150
    reset = datetime.fromisoformat(body["resets_at"])
    assert reset > datetime.now(timezone.utc)
    assert (reset.hour, reset.minute, reset.second) == (0, 0, 0)
