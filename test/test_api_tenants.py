import os

# api.deps reads these at import time.
os.environ.setdefault("GOOGLE_OAUTH_CLIENT_ID", "test-client-id")
os.environ.setdefault("ALLOWED_EMAILS", "test@example.com")

import pytest  # noqa: E402
from starlette.testclient import TestClient  # noqa: E402

import api.main as api_main  # noqa: E402
from api.deps import get_current_owner_uid  # noqa: E402

OWNER = "test@example.com"


@pytest.fixture
def api(monkeypatch):
    added = []
    renamed = []
    deleted = []

    monkeypatch.setattr(api_main, "add_tenant", lambda name, owner_uid: added.append((name, owner_uid)) or "new_id")
    monkeypatch.setattr(
        api_main, "rename_tenant", lambda tenant_id, name, owner_uid: renamed.append((tenant_id, name, owner_uid))
    )
    monkeypatch.setattr(api_main, "delete_tenant", lambda tenant_id, owner_uid: deleted.append((tenant_id, owner_uid)))
    api_main.app.dependency_overrides[get_current_owner_uid] = lambda: OWNER
    yield TestClient(api_main.app), added, renamed, deleted
    api_main.app.dependency_overrides.clear()


def test_post_creates_a_tenant_for_the_authenticated_user(api):
    client, added, _, _ = api

    response = client.post("/tenants", json={"name": "New Project"})

    assert response.status_code == 200
    assert response.json() == {"tenant_id": "new_id"}
    assert added == [("New Project", OWNER)]


@pytest.mark.parametrize("payload", [{}, {"name": ""}, {"name": "x" * 201}, {"name": "ok", "owner_uid": "someone-else"}])
def test_post_rejects_invalid_payloads_and_creates_nothing(api, payload):
    client, added, _, _ = api
    assert client.post("/tenants", json=payload).status_code == 422
    assert added == []


def test_patch_renames_for_the_authenticated_user(api):
    client, _, renamed, _ = api

    response = client.patch("/tenants/proj-1", json={"name": "Renamed"})

    assert response.status_code == 200
    assert response.json() == {"status": "renamed"}
    assert renamed == [("proj-1", "Renamed", OWNER)]


def test_patch_returns_404_for_a_project_that_is_not_the_users(api, monkeypatch):
    client, _, _, _ = api

    def raise_permission_error(tenant_id, name, owner_uid):
        raise PermissionError()

    monkeypatch.setattr(api_main, "rename_tenant", raise_permission_error)

    assert client.patch("/tenants/proj-1", json={"name": "x"}).status_code == 404


def test_delete_removes_for_the_authenticated_user(api):
    client, _, _, deleted = api

    response = client.delete("/tenants/proj-1")

    assert response.status_code == 200
    assert response.json() == {"status": "deleted"}
    assert deleted == [("proj-1", OWNER)]


def test_delete_returns_404_for_a_project_that_is_not_the_users(api, monkeypatch):
    client, _, _, _ = api

    def raise_permission_error(tenant_id, owner_uid):
        raise PermissionError()

    monkeypatch.setattr(api_main, "delete_tenant", raise_permission_error)

    assert client.delete("/tenants/proj-1").status_code == 404


def test_tenant_crud_requires_authentication():
    # No dependency override here: the real token check must run.
    client = TestClient(api_main.app)
    assert client.post("/tenants", json={"name": "x"}).status_code == 401
    assert client.patch("/tenants/proj-1", json={"name": "x"}).status_code == 401
    assert client.delete("/tenants/proj-1").status_code == 401
