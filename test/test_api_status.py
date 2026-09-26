import pytest
from starlette.testclient import TestClient

import api.main as api_main


@pytest.fixture
def api(monkeypatch, signed_in_owner):
    monkeypatch.setattr(api_main, "get_project_jira_status", lambda tenant_id, owner_uid: {"state": "not_linked"})
    monkeypatch.setattr(
        api_main, "get_project_github_status", lambda tenant_id, owner_uid: {"state": "not_connected"}
    )
    return TestClient(api_main.app)


def test_the_status_endpoints_return_what_the_service_says(api):
    assert api.get("/tenants/proj/jira_status").json() == {"state": "not_linked"}
    assert api.get("/tenants/proj/github_status").json() == {"state": "not_connected"}


@pytest.mark.parametrize("name", ["jira_status", "github_status"])
def test_someone_elses_project_is_a_404(api, monkeypatch, name):
    def not_yours(tenant_id, owner_uid):
        raise PermissionError()

    monkeypatch.setattr(api_main, f"get_project_{name}", not_yours)

    assert api.get(f"/tenants/proj/{name}").status_code == 404


@pytest.mark.parametrize("name", ["jira_status", "github_status"])
def test_the_status_endpoints_require_authentication(name):
    assert TestClient(api_main.app).get(f"/tenants/proj/{name}").status_code == 401
