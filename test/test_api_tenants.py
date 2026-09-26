import pytest
from starlette.testclient import TestClient

import api.main as api_main

OWNER = "test@example.com"


@pytest.fixture
def api(monkeypatch, signed_in_owner):
    added = []
    renamed = []
    deleted = []

    monkeypatch.setattr(api_main, "add_tenant", lambda name, owner_uid: added.append((name, owner_uid)) or "new_id")
    monkeypatch.setattr(
        api_main, "rename_tenant", lambda tenant_id, name, owner_uid: renamed.append((tenant_id, name, owner_uid))
    )
    monkeypatch.setattr(api_main, "delete_tenant", lambda tenant_id, owner_uid: deleted.append((tenant_id, owner_uid)))
    yield TestClient(api_main.app), added, renamed, deleted


def test_post_creates_a_tenant_for_the_authenticated_user(api):
    client, added, _, _ = api

    response = client.post("/tenants", json={"name": "New Project"})

    assert response.status_code == 200
    assert response.json() == {"tenant_id": "new_id"}
    assert added == [("New Project", OWNER)]


def test_post_answers_409_when_the_name_is_taken(api, monkeypatch):
    client, _, _, _ = api

    def taken(name, owner_uid):
        raise api_main.TenantNameTaken("That project name isn't available.")

    monkeypatch.setattr(api_main, "add_tenant", taken)

    response = client.post("/tenants", json={"name": "Taken"})

    assert response.status_code == 409
    # Nothing about whose project it is.
    assert response.json() == {"detail": "That project name isn't available. Try another name."}


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


# --- Which GitHub repo / Jira project a project is linked to (APPCE-107)


@pytest.fixture
def links(monkeypatch, signed_in_owner):
    calls = []
    monkeypatch.setattr(
        api_main, "set_github_repo", lambda tenant_id, repo, owner_uid: calls.append(("set_repo", tenant_id, repo, owner_uid))
    )
    monkeypatch.setattr(api_main, "clear_github_repo", lambda tenant_id, owner_uid: calls.append(("clear_repo", tenant_id, owner_uid)))
    monkeypatch.setattr(
        api_main, "set_jira_project_key", lambda tenant_id, key, owner_uid: calls.append(("set_key", tenant_id, key, owner_uid))
    )
    monkeypatch.setattr(api_main, "clear_jira_project_key", lambda tenant_id, owner_uid: calls.append(("clear_key", tenant_id, owner_uid)))
    return TestClient(api_main.app), calls


def test_put_links_a_github_repo_for_the_authenticated_user(links):
    client, calls = links

    response = client.put("/tenants/proj/github_repo", json={"github_repo": "owner/repo"})

    assert response.status_code == 200
    assert response.json() == {"github_repo": "owner/repo"}
    assert calls == [("set_repo", "proj", "owner/repo", OWNER)]


def test_delete_unlinks_the_github_repo(links):
    client, calls = links

    response = client.delete("/tenants/proj/github_repo")

    assert response.status_code == 200
    assert response.json() == {"github_repo": None}
    assert calls == [("clear_repo", "proj", OWNER)]


def test_put_links_a_jira_project_key(links):
    client, calls = links

    response = client.put("/tenants/proj/jira_project_key", json={"jira_project_key": "APPCE"})

    assert response.status_code == 200
    assert response.json() == {"jira_project_key": "APPCE"}
    assert calls == [("set_key", "proj", "APPCE", OWNER)]


def test_delete_unlinks_the_jira_project_key(links):
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
    # The real validators run here: they reject before anything touches Firestore.
    def no_database(*args, **kwargs):
        raise AssertionError("an invalid value must not reach the database")

    monkeypatch.setattr("src.tenants.get_client", no_database)

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
    def not_yours(*args, **kwargs):
        raise PermissionError("No project")

    for name in ("set_github_repo", "clear_github_repo", "set_jira_project_key", "clear_jira_project_key"):
        monkeypatch.setattr(api_main, name, not_yours)

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
    client, calls = links

    assert client.put(path, json=body).status_code == 422
    assert calls == []


def test_linking_requires_authentication(links):
    client, calls = links
    api_main.app.dependency_overrides.clear()

    assert client.put("/tenants/proj/github_repo", json={"github_repo": "owner/repo"}).status_code == 401
    assert client.delete("/tenants/proj/jira_project_key").status_code == 401
    assert calls == []
