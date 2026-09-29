from datetime import datetime, timezone

import pytest
from starlette.testclient import TestClient

import api.main as api_main
from api.deps import get_current_owner_uid
from api.routers import admin

OWNER = "test@example.com"
NON_OWNER = "someone-else@example.com"


@pytest.fixture
def api(monkeypatch):
    state = {"connections": []}
    monkeypatch.setattr(admin, "list_broken_github_connections", lambda: state["connections"])
    yield TestClient(api_main.app), state


def test_owner_sees_an_empty_list_when_nothing_is_broken(api):
    client, _ = api
    api_main.app.dependency_overrides[get_current_owner_uid] = lambda: OWNER

    response = client.get("/admin/connections/broken")

    assert response.status_code == 200
    assert response.json() == {"connections": []}


def test_owner_sees_broken_connections(api):
    client, state = api
    api_main.app.dependency_overrides[get_current_owner_uid] = lambda: OWNER
    state["connections"] = [
        {
            "owner_uid": "user-a",
            "tenant_id": "bd2026",
            "name": "BD2026",
            "kind": "auth",
            "failed_at": datetime(2026, 9, 28, 12, 0, tzinfo=timezone.utc),
        }
    ]

    response = client.get("/admin/connections/broken")

    assert response.json() == {
        "connections": [
            {
                "owner_uid": "user-a",
                "tenant_id": "bd2026",
                "name": "BD2026",
                "kind": "auth",
                "failed_at": "2026-09-28T12:00:00+00:00",
            }
        ]
    }


def test_non_owner_cannot_see_broken_connections(api):
    client, _ = api
    api_main.app.dependency_overrides[get_current_owner_uid] = lambda: NON_OWNER

    assert client.get("/admin/connections/broken").status_code == 403
