"""Tests for the GET /tenants/{tenant_id}/jira_status and /github_status endpoints."""

import pytest
from starlette.testclient import TestClient

import api.main as api_main
from api.routers import status as status_router


@pytest.fixture
def api(monkeypatch, signed_in_owner):
    """Stub the Jira and GitHub project status lookups with fixed states and return a TestClient."""
    monkeypatch.setattr(
        status_router,
        "get_project_jira_status",
        lambda tenant_id, owner_uid: {"state": "not_linked"},
    )
    monkeypatch.setattr(
        status_router,
        "get_project_github_status",
        lambda tenant_id, owner_uid: {"state": "not_connected"},
    )
    return TestClient(api_main.app)


def test_the_status_endpoints_return_what_the_service_says(api):
    """Both status endpoints return the state reported by the underlying service."""
    assert api.get("/tenants/proj/jira_status").json() == {"state": "not_linked"}
    assert api.get("/tenants/proj/github_status").json() == {"state": "not_connected"}


@pytest.mark.parametrize("name", ["jira_status", "github_status"])
def test_someone_elses_project_is_a_404(api, monkeypatch, name):
    """Both status endpoints return 404 for a project not owned by the authenticated user."""

    def not_yours(tenant_id, owner_uid):
        """Raise PermissionError to simulate a project the user doesn't own."""
        raise PermissionError()

    monkeypatch.setattr(status_router, f"get_project_{name}", not_yours)

    assert api.get(f"/tenants/proj/{name}").status_code == 404


@pytest.mark.parametrize("name", ["jira_status", "github_status"])
def test_the_status_endpoints_require_authentication(name):
    """Both status endpoints return 401 without a valid auth token."""
    assert TestClient(api_main.app).get(f"/tenants/proj/{name}").status_code == 401
