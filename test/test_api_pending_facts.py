import pytest
from starlette.testclient import TestClient

import api.main as api_main

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
    approved = []
    rejected = []

    def fake_approve(tenant_id, pending_fact_id, owner_uid):
        approved.append((tenant_id, pending_fact_id, owner_uid))

    def fake_reject(tenant_id, pending_fact_id, owner_uid):
        rejected.append((tenant_id, pending_fact_id, owner_uid))

    monkeypatch.setattr(api_main, "list_pending_facts", lambda tenant_id, owner_uid: list(PENDING))
    monkeypatch.setattr(api_main, "approve_pending_fact", fake_approve)
    monkeypatch.setattr(api_main, "reject_pending_fact", fake_reject)
    yield TestClient(api_main.app), approved, rejected


def test_get_returns_the_pending_facts_for_the_project(api):
    client, _, _ = api
    response = client.get("/tenants/proj-1/pending_facts")

    assert response.status_code == 200
    assert response.json() == PENDING


def test_get_returns_404_for_a_project_that_is_not_the_users(api, monkeypatch):
    client, _, _ = api

    def raise_permission_error(tenant_id, owner_uid):
        raise PermissionError()

    monkeypatch.setattr(api_main, "list_pending_facts", raise_permission_error)

    assert client.get("/tenants/proj-1/pending_facts").status_code == 404


def test_post_approve_calls_through_for_the_authenticated_user(api):
    client, approved, _ = api

    response = client.post("/tenants/proj-1/pending_facts/p1/approve")

    assert response.status_code == 200
    assert response.json() == {"status": "approved"}
    assert approved == [("proj-1", "p1", OWNER)]


def test_post_approve_returns_404_for_a_missing_pending_fact(api, monkeypatch):
    client, _, _ = api

    def raise_value_error(tenant_id, pending_fact_id, owner_uid):
        raise ValueError("nope")

    monkeypatch.setattr(api_main, "approve_pending_fact", raise_value_error)

    assert client.post("/tenants/proj-1/pending_facts/missing/approve").status_code == 404


def test_delete_rejects_for_the_authenticated_user(api):
    client, _, rejected = api

    response = client.delete("/tenants/proj-1/pending_facts/p1")

    assert response.status_code == 200
    assert response.json() == {"status": "rejected"}
    assert rejected == [("proj-1", "p1", OWNER)]


def test_pending_facts_require_authentication():
    # No dependency override here: the real token check must run.
    client = TestClient(api_main.app)
    assert client.get("/tenants/proj-1/pending_facts").status_code == 401
    assert client.post("/tenants/proj-1/pending_facts/p1/approve").status_code == 401
    assert client.delete("/tenants/proj-1/pending_facts/p1").status_code == 401
