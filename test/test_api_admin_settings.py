"""Tests for the GET/PUT /admin/settings endpoints."""

import pytest
from starlette.testclient import TestClient

import api.main as api_main
from api.deps import get_current_owner_uid
from api.routers import admin
from src.accounts.settings import BOUNDS, DEFAULTS

OWNER = "test@example.com"
NON_OWNER = "someone-else@example.com"
CURRENT = {"history_turns": 20, "daily_message_warning_threshold": 100}


@pytest.fixture
def api(monkeypatch):
    """Patch get_settings/save_settings to read and write an in-memory copy of CURRENT, and yield a TestClient for api.main.app."""
    monkeypatch.setattr(admin, "get_settings", lambda: dict(CURRENT))
    monkeypatch.setattr(admin, "save_settings", lambda settings: dict(settings))
    yield TestClient(api_main.app)


def test_owner_can_read_the_shared_settings(api):
    """The owner can GET /admin/settings and see the current values, defaults, and bounds."""
    api_main.app.dependency_overrides[get_current_owner_uid] = lambda: OWNER

    response = api.get("/admin/settings")

    assert response.status_code == 200
    body = response.json()
    assert (body["history_turns"], body["daily_message_warning_threshold"]) == (20, 100)
    assert body["defaults"] == DEFAULTS
    assert body["limits"]["history_turns"] == {"min": BOUNDS["history_turns"][0], "max": BOUNDS["history_turns"][1]}


def test_owner_can_set_the_shared_settings(api):
    """The owner can PUT new shared settings and see the saved value reflected in the response."""
    api_main.app.dependency_overrides[get_current_owner_uid] = lambda: OWNER

    response = api.put("/admin/settings", json={"history_turns": 5, "daily_message_warning_threshold": 40})

    assert response.status_code == 200
    assert response.json()["history_turns"] == 5


def test_non_owner_cannot_read_or_write_the_shared_settings(api):
    """A non-owner gets a 403 on both GET and PUT /admin/settings."""
    api_main.app.dependency_overrides[get_current_owner_uid] = lambda: NON_OWNER

    assert api.get("/admin/settings").status_code == 403
    assert api.put("/admin/settings", json={"history_turns": 5, "daily_message_warning_threshold": 40}).status_code == 403


@pytest.mark.parametrize(
    "payload",
    [
        {"history_turns": 0, "daily_message_warning_threshold": 40},
        {"history_turns": BOUNDS["history_turns"][1] + 1, "daily_message_warning_threshold": 40},
        {"history_turns": 5, "daily_message_warning_threshold": 0},
        {"history_turns": "5", "daily_message_warning_threshold": 40},
        {"history_turns": True, "daily_message_warning_threshold": 40},
        {"history_turns": 5},
        {"history_turns": 5, "daily_message_warning_threshold": 40, "extra": "nope"},
    ],
)
def test_invalid_payloads_are_rejected(api, payload):
    """PUT /admin/settings rejects out-of-bounds, wrong-typed, missing, or extra fields with a 422."""
    api_main.app.dependency_overrides[get_current_owner_uid] = lambda: OWNER

    assert api.put("/admin/settings", json=payload).status_code == 422
