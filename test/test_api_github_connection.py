"""Tests for the GET/PUT/DELETE /github/connection endpoints."""

import pytest
from starlette.testclient import TestClient

import api.main as api_main
from api.routers import connections

OWNER = "test@example.com"


@pytest.fixture
def api(monkeypatch, signed_in_owner):
    """Stub GitHub token validation, saving, and deletion, and return a TestClient plus the recorded save/delete calls."""
    saved = []
    deleted = []

    def fake_save(owner_uid, token):
        """Record the owner_uid and token that would have been saved."""
        saved.append((owner_uid, token))

    def fake_delete(owner_uid):
        """Record the owner_uid whose connection would have been deleted."""
        deleted.append(owner_uid)

    monkeypatch.setattr(connections, "validate_github_token", lambda token: None)
    monkeypatch.setattr(connections, "save_github_token", fake_save)
    monkeypatch.setattr(connections, "delete_github_connection", fake_delete)
    yield TestClient(api_main.app), saved, deleted


def test_get_reports_connected_when_a_token_is_on_file(api, monkeypatch):
    """GET reports connected: true when a GitHub token is stored for the user."""
    client, _, _ = api
    monkeypatch.setattr(connections, "has_github_connection", lambda owner_uid: True)

    assert client.get("/github/connection").json() == {"connected": True}


def test_get_reports_disconnected_when_no_token_is_on_file(api, monkeypatch):
    """GET reports connected: false when no GitHub token is stored for the user."""
    client, _, _ = api
    monkeypatch.setattr(connections, "has_github_connection", lambda owner_uid: False)

    assert client.get("/github/connection").json() == {"connected": False}


def test_put_validates_then_saves_for_the_authenticated_user(api):
    """PUT validates the token, then saves it for the signed-in owner and reports connected: true."""
    client, saved, _ = api

    response = client.put("/github/connection", json={"token": "github_pat_example"})

    assert response.status_code == 200
    assert response.json() == {"connected": True}
    assert saved == [(OWNER, "github_pat_example")]


def test_put_rejects_a_token_validate_raises_on_and_saves_nothing(api, monkeypatch):
    """PUT returns 400 and saves nothing when token validation raises."""
    client, saved, _ = api
    monkeypatch.setattr(
        connections,
        "validate_github_token",
        lambda token: (_ for _ in ()).throw(ValueError("nope")),
    )

    response = client.put("/github/connection", json={"token": "ghp_classic"})

    assert response.status_code == 400
    assert saved == []


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"token": ""},
        {"token": "x" * 256},
        {"token": "github_pat_example", "owner_uid": "someone-else@example.com"},
    ],
)
def test_put_rejects_invalid_payloads_and_saves_nothing(api, payload):
    """PUT rejects an empty, oversized, or owner_uid-overriding payload with 422 and saves nothing."""
    client, saved, _ = api
    assert client.put("/github/connection", json=payload).status_code == 422
    assert saved == []


def test_delete_disconnects_the_authenticated_user(api):
    """DELETE removes the signed-in owner's GitHub connection and reports connected: false."""
    client, _, deleted = api

    response = client.delete("/github/connection")

    assert response.status_code == 200
    assert response.json() == {"connected": False}
    assert deleted == [OWNER]


def test_github_connection_requires_authentication():
    """GET, PUT, and DELETE all return 401 without a valid auth token."""
    # No dependency override here: the real token check must run.
    client = TestClient(api_main.app)
    assert client.get("/github/connection").status_code == 401
    assert client.put("/github/connection", json={"token": "x"}).status_code == 401
    assert client.delete("/github/connection").status_code == 401
