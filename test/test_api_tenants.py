"""Tests for the /tenants CRUD endpoints and their GitHub/Jira link routes."""

import pytest
from starlette.testclient import TestClient

import api.main as api_main
from api.routers import tenants as tenants_router
from src.projects.tenants import TenantNameTaken

OWNER = "test@example.com"


@pytest.fixture
def api(monkeypatch, signed_in_owner):
    """Stub out the tenants router's add/rename/delete calls and return a
    client plus the lists each stub appends its calls to."""
    added = []
    renamed = []
    deleted = []

    monkeypatch.setattr(tenants_router, "add_tenant", lambda name, owner_uid: added.append((name, owner_uid)) or "new_id")
    monkeypatch.setattr(
        tenants_router, "rename_tenant", lambda tenant_id, name, owner_uid: renamed.append((tenant_id, name, owner_uid))
    )
    monkeypatch.setattr(tenants_router, "delete_tenant", lambda tenant_id, owner_uid: deleted.append((tenant_id, owner_uid)))
    yield TestClient(api_main.app), added, renamed, deleted


def test_post_creates_a_tenant_for_the_authenticated_user(api):
    """POST /tenants creates a tenant owned by the signed-in user and returns its id."""
    client, added, _, _ = api

    response = client.post("/tenants", json={"name": "New Project"})

    assert response.status_code == 200
    assert response.json() == {"tenant_id": "new_id"}
    assert added == [("New Project", OWNER)]


def test_post_answers_409_when_the_name_is_taken(api, monkeypatch):
    """A taken tenant name answers 409 with a generic message, not one that
    reveals whose project already has that name."""
    client, _, _, _ = api

    def taken(name, owner_uid):
        """Simulate add_tenant rejecting an already-used tenant name."""
        raise TenantNameTaken("That project name isn't available.")

    monkeypatch.setattr(tenants_router, "add_tenant", taken)

    response = client.post("/tenants", json={"name": "Taken"})

    assert response.status_code == 409
    # Nothing about whose project it is.
    assert response.json() == {"detail": "That project name isn't available. Try another name."}


@pytest.mark.parametrize("payload", [{}, {"name": ""}, {"name": "x" * 201}, {"name": "ok", "owner_uid": "someone-else"}])
def test_post_rejects_invalid_payloads_and_creates_nothing(api, payload):
    """An empty, too-long, missing, or owner_uid-spoofing POST body is
    rejected with 422 before any tenant is created."""
    client, added, _, _ = api
    assert client.post("/tenants", json=payload).status_code == 422
    assert added == []


def test_patch_renames_for_the_authenticated_user(api):
    """PATCH /tenants/{id} renames the tenant for the signed-in owner."""
    client, _, renamed, _ = api

    response = client.patch("/tenants/proj-1", json={"name": "Renamed"})

    assert response.status_code == 200
    assert response.json() == {"status": "renamed"}
    assert renamed == [("proj-1", "Renamed", OWNER)]


def test_patch_returns_404_for_a_project_that_is_not_the_users(api, monkeypatch):
    """PATCH answers 404, not 403, when rename_tenant raises PermissionError
    for a tenant the caller doesn't own."""
    client, _, _, _ = api

    def raise_permission_error(tenant_id, name, owner_uid):
        """Simulate rename_tenant refusing a tenant the caller doesn't own."""
        raise PermissionError()

    monkeypatch.setattr(tenants_router, "rename_tenant", raise_permission_error)

    assert client.patch("/tenants/proj-1", json={"name": "x"}).status_code == 404


def test_delete_removes_for_the_authenticated_user(api):
    """DELETE /tenants/{id} removes the tenant for the signed-in owner."""
    client, _, _, deleted = api

    response = client.delete("/tenants/proj-1")

    assert response.status_code == 200
    assert response.json() == {"status": "deleted"}
    assert deleted == [("proj-1", OWNER)]


def test_delete_returns_404_for_a_project_that_is_not_the_users(api, monkeypatch):
    """DELETE answers 404, not 403, when delete_tenant raises PermissionError
    for a tenant the caller doesn't own."""
    client, _, _, _ = api

    def raise_permission_error(tenant_id, owner_uid):
        """Simulate delete_tenant refusing a tenant the caller doesn't own."""
        raise PermissionError()

    monkeypatch.setattr(tenants_router, "delete_tenant", raise_permission_error)

    assert client.delete("/tenants/proj-1").status_code == 404


def test_tenant_crud_requires_authentication():
    """POST/PATCH/DELETE on /tenants all answer 401 without a valid auth token."""
    # No dependency override here: the real token check must run.
    client = TestClient(api_main.app)
    assert client.post("/tenants", json={"name": "x"}).status_code == 401
    assert client.patch("/tenants/proj-1", json={"name": "x"}).status_code == 401
    assert client.delete("/tenants/proj-1").status_code == 401


# --- Which GitHub repo / Jira project a project is linked to (APPCE-107)


@pytest.fixture
def links(monkeypatch, signed_in_owner):
    """Stub out the GitHub repo/Jira project key set/clear calls and return
    a client plus the list each stub appends its calls to."""
    calls = []
    monkeypatch.setattr(
        tenants_router, "set_github_repo", lambda tenant_id, repo, owner_uid: calls.append(("set_repo", tenant_id, repo, owner_uid))
    )
    monkeypatch.setattr(tenants_router, "clear_github_repo", lambda tenant_id, owner_uid: calls.append(("clear_repo", tenant_id, owner_uid)))
    monkeypatch.setattr(
        tenants_router, "set_jira_project_key", lambda tenant_id, key, owner_uid: calls.append(("set_key", tenant_id, key, owner_uid))
    )
    monkeypatch.setattr(tenants_router, "clear_jira_project_key", lambda tenant_id, owner_uid: calls.append(("clear_key", tenant_id, owner_uid)))
    return TestClient(api_main.app), calls


def test_put_links_a_github_repo_for_the_authenticated_user(links):
    """PUT /tenants/{id}/github_repo links the repo for the signed-in owner."""
    client, calls = links

    response = client.put("/tenants/proj/github_repo", json={"github_repo": "owner/repo"})

    assert response.status_code == 200
    assert response.json() == {"github_repo": "owner/repo"}
    assert calls == [("set_repo", "proj", "owner/repo", OWNER)]


def test_delete_unlinks_the_github_repo(links):
    """DELETE /tenants/{id}/github_repo clears the linked repo."""
    client, calls = links

    response = client.delete("/tenants/proj/github_repo")

    assert response.status_code == 200
    assert response.json() == {"github_repo": None}
    assert calls == [("clear_repo", "proj", OWNER)]


def test_put_links_a_jira_project_key(links):
    """PUT /tenants/{id}/jira_project_key links the key for the signed-in owner."""
    client, calls = links

    response = client.put("/tenants/proj/jira_project_key", json={"jira_project_key": "APPCE"})

    assert response.status_code == 200
    assert response.json() == {"jira_project_key": "APPCE"}
    assert calls == [("set_key", "proj", "APPCE", OWNER)]


def test_delete_unlinks_the_jira_project_key(links):
    """DELETE /tenants/{id}/jira_project_key clears the linked key."""
    client, calls = links

    assert client.delete("/tenants/proj/jira_project_key").json() == {"jira_project_key": None}
    assert calls == [("clear_key", "proj", OWNER)]


@pytest.mark.parametrize(
    "path, body",
    [
        ("/tenants/proj/github_repo", {"github_repo": "not a repo"}),
        ("/tenants/proj/github_repo", {"github_repo": "https://github.com/owner/repo"}),
        ("/tenants/proj/jira_project_key", {"jira_project_key": "appce"}),
        ("/tenants/proj/jira_project_key", {"jira_project_key": 'X" OR project != "'}),
    ],
)
def test_an_invalid_value_is_a_400_with_the_reason_and_nothing_is_saved(monkeypatch, signed_in_owner, path, body):
    """A malformed GitHub repo or Jira project key value is rejected with a
    400 and its reason before it ever reaches Firestore."""
    # The real validators run here: they reject before anything touches Firestore.
    def no_database(*args, **kwargs):
        """Fail the test if validation lets an invalid value reach the database."""
        raise AssertionError("an invalid value must not reach the database")

    monkeypatch.setattr("src.projects.tenants.get_client", no_database)

    response = TestClient(api_main.app).put(path, json=body)

    assert response.status_code == 400
    assert response.json()["detail"]


@pytest.mark.parametrize(
    "method, path, body",
    [
        ("put", "/tenants/proj/github_repo", {"github_repo": "owner/repo"}),
        ("delete", "/tenants/proj/github_repo", None),
        ("put", "/tenants/proj/jira_project_key", {"jira_project_key": "APPCE"}),
        ("delete", "/tenants/proj/jira_project_key", None),
    ],
)
def test_someone_elses_or_a_missing_project_is_a_404(monkeypatch, signed_in_owner, method, path, body):
    """Linking or unlinking a repo/key on a tenant that isn't the caller's
    (or doesn't exist) answers 404."""
    def not_yours(*args, **kwargs):
        """Simulate the link/unlink call refusing a tenant the caller doesn't own."""
        raise PermissionError("No project")

    for name in ("set_github_repo", "clear_github_repo", "set_jira_project_key", "clear_jira_project_key"):
        monkeypatch.setattr(tenants_router, name, not_yours)

    response = getattr(TestClient(api_main.app), method)(path, **({"json": body} if body else {}))

    assert response.status_code == 404


@pytest.mark.parametrize(
    "path, body",
    [
        ("/tenants/proj/github_repo", {"github_repo": ""}),
        ("/tenants/proj/github_repo", {"github_repo": "owner/repo", "extra": 1}),
        ("/tenants/proj/github_repo", {}),
        ("/tenants/proj/jira_project_key", {"jira_project_key": 5}),
    ],
)
def test_a_malformed_body_is_rejected(links, path, body):
    """An empty, extra-field, missing, or wrong-typed link request body is
    rejected with 422 before any set/clear call runs."""
    client, calls = links

    assert client.put(path, json=body).status_code == 422
    assert calls == []


def test_linking_requires_authentication(links):
    """PUT/DELETE on the GitHub repo and Jira project key routes both
    answer 401 without a valid auth token."""
    client, calls = links
    api_main.app.dependency_overrides.clear()

    assert client.put("/tenants/proj/github_repo", json={"github_repo": "owner/repo"}).status_code == 401
    assert client.delete("/tenants/proj/jira_project_key").status_code == 401
    assert calls == []
