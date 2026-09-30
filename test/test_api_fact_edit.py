"""Tests for the PATCH/DELETE /tenants/{tenant_id}/facts/{fact_id} endpoints."""

import pytest
from starlette.testclient import TestClient

import api.main as api_main
from api.routers import facts as facts_router

OWNER = "test@example.com"


@pytest.fixture
def api(monkeypatch, signed_in_owner):
    """Stub get_fact/update_fact/delete_fact and return a TestClient plus the list of recorded update/delete calls."""
    calls = []
    monkeypatch.setattr(
        facts_router, "get_fact", lambda tenant_id, fact_id, owner_uid: {"fact_id": fact_id}
    )
    monkeypatch.setattr(
        facts_router,
        "update_fact",
        lambda tenant_id, fact_id, owner_uid, content=None, category=None: calls.append(
            ("update", tenant_id, fact_id, owner_uid, content, category)
        ),
    )
    monkeypatch.setattr(
        facts_router,
        "delete_fact",
        lambda tenant_id, fact_id, owner_uid: calls.append(
            ("delete", tenant_id, fact_id, owner_uid)
        ),
    )
    return TestClient(api_main.app), calls


def test_patch_updates_a_fact_for_the_authenticated_user(api):
    """PATCH updates the fact's content for the signed-in owner and returns status "updated"."""
    client, calls = api

    response = client.patch("/tenants/proj/facts/f1", json={"content": "Uses MySQL"})

    assert response.status_code == 200
    assert response.json() == {"status": "updated"}
    assert calls == [("update", "proj", "f1", OWNER, "Uses MySQL", None)]


def test_patch_can_change_only_the_category(api):
    """PATCH with only a category updates the category and leaves content unset."""
    client, calls = api

    assert client.patch("/tenants/proj/facts/f1", json={"category": "decision"}).status_code == 200
    assert calls == [("update", "proj", "f1", OWNER, None, "decision")]


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"content": ""},
        {"content": "x" * 2001},
        {"content": "ok", "owner_uid": "x"},
        {"content": 5},
    ],
)
def test_patch_rejects_a_bad_body_and_changes_nothing(api, body):
    """An empty, oversized, wrong-typed, or owner_uid-overriding PATCH body is rejected with 422 and updates nothing."""
    client, calls = api

    assert client.patch("/tenants/proj/facts/f1", json=body).status_code == 422
    assert calls == []


def test_patch_with_an_unknown_category_is_a_400_with_the_reason(api, monkeypatch):
    """A PATCH to an unknown category is rejected with 400, and the response includes the invalid category name."""
    client, _ = api

    def refuse(*args, **kwargs):
        """Raise a ValueError naming the rejected category."""
        raise ValueError("Invalid category 'nope'")

    monkeypatch.setattr(facts_router, "update_fact", refuse)

    response = client.patch("/tenants/proj/facts/f1", json={"category": "nope"})

    assert response.status_code == 400
    assert "nope" in response.json()["detail"]


def test_delete_removes_a_fact(api):
    """DELETE removes the fact for the signed-in owner and returns status "deleted"."""
    client, calls = api

    response = client.delete("/tenants/proj/facts/f1")

    assert response.status_code == 200
    assert response.json() == {"status": "deleted"}
    assert calls == [("delete", "proj", "f1", OWNER)]


@pytest.mark.parametrize("error", [PermissionError("not yours"), LookupError("no such fact")])
def test_someone_elses_project_or_a_missing_fact_is_a_404_and_nothing_changes(
    api, monkeypatch, error
):
    """PATCH and DELETE both return 404 and make no changes when the fact isn't owned by the user or doesn't exist."""
    client, calls = api

    def missing(*args, **kwargs):
        """Raise the parametrized error to simulate a not-owned or missing fact."""
        raise error

    monkeypatch.setattr(facts_router, "get_fact", missing)

    assert client.patch("/tenants/proj/facts/f1", json={"content": "x"}).status_code == 404
    assert client.delete("/tenants/proj/facts/f1").status_code == 404
    assert calls == []


def test_fact_edits_require_authentication():
    """PATCH and DELETE both return 401 without a valid auth token."""
    client = TestClient(api_main.app)

    assert client.patch("/tenants/proj/facts/f1", json={"content": "x"}).status_code == 401
    assert client.delete("/tenants/proj/facts/f1").status_code == 401
