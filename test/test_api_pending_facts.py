"""Tests for the GET/POST/DELETE /tenants/{tenant_id}/pending_facts endpoints and their stats sub-endpoint."""

import pytest
from starlette.testclient import TestClient

import api.main as api_main
from api.routers import pending

OWNER = "test@example.com"
PENDING = [
    {
        "pending_fact_id": "p1",
        "content": "Uses Postgres",
        "category": "architecture",
        "source": "github",
        "source_url": "https://github.com/o/r/pull/1",
        "created_at": None,
    }
]


@pytest.fixture
def api(monkeypatch, signed_in_owner):
    """Stub the pending-facts service functions with fixed data and recorded calls, and return a TestClient plus the approved/rejected call lists."""
    approved = []
    rejected = []

    def fake_approve(tenant_id, pending_fact_id, owner_uid):
        """Record the call's arguments instead of approving a real pending fact."""
        approved.append((tenant_id, pending_fact_id, owner_uid))

    def fake_reject(tenant_id, pending_fact_id, owner_uid):
        """Record the call's arguments instead of rejecting a real pending fact."""
        rejected.append((tenant_id, pending_fact_id, owner_uid))

    monkeypatch.setattr(pending, "list_pending_facts", lambda tenant_id, owner_uid: list(PENDING))
    monkeypatch.setattr(pending, "approve_pending_fact", fake_approve)
    monkeypatch.setattr(pending, "reject_pending_fact", fake_reject)
    monkeypatch.setattr(
        pending, "get_pending_fact_stats", lambda tenant_id, owner_uid: {"pending": 1, "approved": 7, "rejected": 3}
    )
    yield TestClient(api_main.app), approved, rejected


def test_get_returns_the_pending_facts_for_the_project(api):
    """GET returns the project's pending facts as-is."""
    client, _, _ = api
    response = client.get("/tenants/proj-1/pending_facts")

    assert response.status_code == 200
    assert response.json() == PENDING


def test_get_returns_404_for_a_project_that_is_not_the_users(api, monkeypatch):
    """GET returns 404 for a project not owned by the authenticated user."""
    client, _, _ = api

    def raise_permission_error(tenant_id, owner_uid):
        """Raise PermissionError to simulate a project the user doesn't own."""
        raise PermissionError()

    monkeypatch.setattr(pending, "list_pending_facts", raise_permission_error)

    assert client.get("/tenants/proj-1/pending_facts").status_code == 404


def test_post_approve_calls_through_for_the_authenticated_user(api):
    """POST approve calls through with the signed-in owner and returns status "approved"."""
    client, approved, _ = api

    response = client.post("/tenants/proj-1/pending_facts/p1/approve")

    assert response.status_code == 200
    assert response.json() == {"status": "approved"}
    assert approved == [("proj-1", "p1", OWNER)]


def test_post_approve_returns_404_for_a_missing_pending_fact(api, monkeypatch):
    """POST approve returns 404 when the pending fact does not exist."""
    client, _, _ = api

    def raise_value_error(tenant_id, pending_fact_id, owner_uid):
        """Raise ValueError to simulate a missing pending fact."""
        raise ValueError("nope")

    monkeypatch.setattr(pending, "approve_pending_fact", raise_value_error)

    assert client.post("/tenants/proj-1/pending_facts/missing/approve").status_code == 404


def test_delete_rejects_for_the_authenticated_user(api):
    """DELETE rejects the pending fact for the signed-in owner and returns status "rejected"."""
    client, _, rejected = api

    response = client.delete("/tenants/proj-1/pending_facts/p1")

    assert response.status_code == 200
    assert response.json() == {"status": "rejected"}
    assert rejected == [("proj-1", "p1", OWNER)]


def test_pending_facts_require_authentication():
    """GET, POST approve, and DELETE all return 401 without a valid auth token."""
    # No dependency override here: the real token check must run.
    client = TestClient(api_main.app)
    assert client.get("/tenants/proj-1/pending_facts").status_code == 401
    assert client.post("/tenants/proj-1/pending_facts/p1/approve").status_code == 401
    assert client.delete("/tenants/proj-1/pending_facts/p1").status_code == 401


def test_stats_return_the_counts_for_the_project(api):
    """GET stats returns the pending/approved/rejected counts for the project."""
    client, _, _ = api

    response = client.get("/tenants/proj-1/pending_facts/stats")

    assert response.status_code == 200
    assert response.json() == {"pending": 1, "approved": 7, "rejected": 3}


def test_stats_of_a_project_that_is_not_the_users_are_a_404(api, monkeypatch):
    """GET stats returns 404 for a project not owned by the authenticated user."""
    client, _, _ = api

    def not_yours(tenant_id, owner_uid):
        """Raise PermissionError to simulate a project the user doesn't own."""
        raise PermissionError()

    monkeypatch.setattr(pending, "get_pending_fact_stats", not_yours)

    assert client.get("/tenants/proj-1/pending_facts/stats").status_code == 404


def test_stats_require_authentication():
    """GET stats returns 401 without a valid auth token."""
    from starlette.testclient import TestClient as _Client

    assert _Client(api_main.app).get("/tenants/proj-1/pending_facts/stats").status_code == 401
