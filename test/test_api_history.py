"""Tests for the GET /tenants/{tenant_id}/history endpoint."""

from datetime import datetime, timezone

import pytest
from starlette.testclient import TestClient

import api.main as api_main
from api.routers import chat as chat_router

OWNER = "test@example.com"


@pytest.fixture
def client(monkeypatch, signed_in_owner):
    """Stub load_recent_turns to return one fixed chat turn, and return a TestClient recording the calls it received."""
    calls = []

    def fake_load(tenant_id, owner_uid, limit):
        """Record the call's arguments and return one fixed chat turn."""
        calls.append((tenant_id, owner_uid, limit))
        return [
            {
                "question": "q",
                "answer": "a",
                "created_at": datetime(2026, 9, 21, 12, 0, tzinfo=timezone.utc),
            }
        ]

    monkeypatch.setattr(chat_router, "load_recent_turns", fake_load)
    test_client = TestClient(api_main.app)
    test_client.calls = calls
    yield test_client


def test_history_returns_the_saved_turns_for_the_authenticated_user(client):
    """GET returns the saved chat turns, with created_at serialized to an ISO 8601 UTC string."""
    response = client.get("/tenants/some_tenant/history")

    assert response.status_code == 200
    assert response.json() == [{"question": "q", "answer": "a", "created_at": "2026-09-21T12:00:00Z"}]
    assert client.calls == [("some_tenant", OWNER, chat_router.CHAT_HISTORY_DISPLAY_TURNS)]


def test_history_of_a_project_the_user_does_not_own_is_a_404(client, monkeypatch):
    """GET returns 404 for a tenant the authenticated user does not own."""

    def not_owned(tenant_id, owner_uid, limit):
        """Raise PermissionError to simulate a project the user doesn't own."""
        raise PermissionError("nope")

    monkeypatch.setattr(chat_router, "load_recent_turns", not_owned)

    assert client.get("/tenants/not_mine/history").status_code == 404


def test_history_requires_authentication():
    """GET returns 401 without a valid auth token."""
    # No dependency override here: the real token check must run.
    assert TestClient(api_main.app).get("/tenants/some_tenant/history").status_code == 401
