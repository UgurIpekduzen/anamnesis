import os

# api.deps reads these at import time.
os.environ.setdefault("GOOGLE_OAUTH_CLIENT_ID", "test-client-id")
os.environ.setdefault("ALLOWED_EMAILS", "test@example.com")

from datetime import datetime, timezone  # noqa: E402

import pytest  # noqa: E402
from starlette.testclient import TestClient  # noqa: E402

import api.main as api_main  # noqa: E402
from api.deps import get_current_owner_uid  # noqa: E402

OWNER = "test@example.com"


@pytest.fixture
def client(monkeypatch):
    calls = []

    def fake_load(tenant_id, owner_uid, limit):
        calls.append((tenant_id, owner_uid, limit))
        return [
            {
                "question": "q",
                "answer": "a",
                "created_at": datetime(2026, 9, 21, 12, 0, tzinfo=timezone.utc),
            }
        ]

    api_main.app.dependency_overrides[get_current_owner_uid] = lambda: OWNER
    monkeypatch.setattr(api_main, "load_recent_turns", fake_load)
    test_client = TestClient(api_main.app)
    test_client.calls = calls
    yield test_client
    api_main.app.dependency_overrides.clear()


def test_history_returns_the_saved_turns_for_the_authenticated_user(client):
    response = client.get("/tenants/some_tenant/history")

    assert response.status_code == 200
    assert response.json() == [{"question": "q", "answer": "a", "created_at": "2026-09-21T12:00:00Z"}]
    assert client.calls == [("some_tenant", OWNER, api_main.CHAT_HISTORY_DISPLAY_TURNS)]


def test_history_of_a_project_the_user_does_not_own_is_a_404(client, monkeypatch):
    def not_owned(tenant_id, owner_uid, limit):
        raise PermissionError("nope")

    monkeypatch.setattr(api_main, "load_recent_turns", not_owned)

    assert client.get("/tenants/not_mine/history").status_code == 404


def test_history_requires_authentication():
    # No dependency override here: the real token check must run.
    assert TestClient(api_main.app).get("/tenants/some_tenant/history").status_code == 401
