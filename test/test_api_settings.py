import os

# api.deps reads these at import time.
os.environ.setdefault("GOOGLE_OAUTH_CLIENT_ID", "test-client-id")
os.environ.setdefault("ALLOWED_EMAILS", "test@example.com")

import pytest  # noqa: E402
from starlette.testclient import TestClient  # noqa: E402

import api.main as api_main  # noqa: E402
from api.deps import get_current_owner_uid  # noqa: E402
from src.settings import BOUNDS, DEFAULTS  # noqa: E402

OWNER = "test@example.com"
CURRENT = {"history_turns": 20, "daily_message_warning_threshold": 100}


@pytest.fixture
def api(monkeypatch):
    saved = []

    def fake_save(owner_uid, settings):
        saved.append((owner_uid, settings))
        return settings

    api_main.app.dependency_overrides[get_current_owner_uid] = lambda: OWNER
    monkeypatch.setattr(api_main, "get_settings", lambda owner_uid: dict(CURRENT))
    monkeypatch.setattr(api_main, "save_settings", fake_save)
    yield TestClient(api_main.app), saved
    api_main.app.dependency_overrides.clear()


def test_get_also_returns_the_defaults_so_the_ui_knows_what_reset_means(api):
    client, _ = api
    assert client.get("/settings").json()["defaults"] == DEFAULTS


def test_delete_resets_the_authenticated_users_settings(api, monkeypatch):
    client, _ = api
    resets = []
    monkeypatch.setattr(
        api_main, "reset_settings", lambda owner_uid: resets.append(owner_uid) or dict(DEFAULTS)
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
    monkeypatch.setattr(api_main, "get_today_count", lambda owner_uid: 3)
    monkeypatch.setattr(
        api_main, "get_settings", lambda owner_uid: {"history_turns": 20, "daily_message_warning_threshold": 7}
    )

    assert client.get("/usage").json() == {"count": 3, "threshold": 7}
