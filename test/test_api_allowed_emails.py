import pytest
from starlette.testclient import TestClient

import api.main as api_main
from api.routers import admin
from api.deps import get_current_owner_uid

OWNER = "test@example.com"
NON_OWNER = "someone-else@example.com"


@pytest.fixture
def api(monkeypatch):
    monkeypatch.setattr(admin, "get_extra_allowed_emails", lambda: {"already-allowed@example.com"})
    monkeypatch.setattr(admin, "add_allowed_email", lambda email: None)
    monkeypatch.setattr(admin, "remove_allowed_email", lambda email: None)
    monkeypatch.setattr(admin, "get_usage_for", lambda emails: [{"email": e, "count": 0} for e in sorted(emails)])
    monkeypatch.setattr(admin, "get_global_today_count", lambda: 0)
    monkeypatch.setattr(admin, "GLOBAL_DAILY_MESSAGE_LIMIT", 1000)
    yield TestClient(api_main.app)


def test_owner_can_list_allowed_emails(api):
    api_main.app.dependency_overrides[get_current_owner_uid] = lambda: OWNER

    response = api.get("/admin/allowed_emails")

    assert response.status_code == 200
    assert response.json() == {
        "owner_emails": [OWNER],
        "extra_emails": ["already-allowed@example.com"],
    }


def test_non_owner_is_rejected_from_every_admin_endpoint(api):
    api_main.app.dependency_overrides[get_current_owner_uid] = lambda: NON_OWNER

    assert api.get("/admin/allowed_emails").status_code == 403
    assert api.post("/admin/allowed_emails", json={"email": "x@example.com"}).status_code == 403
    assert api.delete("/admin/allowed_emails/x@example.com").status_code == 403


def test_owner_can_add_an_email(api):
    api_main.app.dependency_overrides[get_current_owner_uid] = lambda: OWNER

    response = api.post("/admin/allowed_emails", json={"email": "new-user@example.com"})

    assert response.status_code == 200


def test_adding_an_invalid_email_surfaces_the_reason(api, monkeypatch):
    api_main.app.dependency_overrides[get_current_owner_uid] = lambda: OWNER

    def reject(email):
        raise ValueError("This email already has permanent owner access.")

    monkeypatch.setattr(admin, "add_allowed_email", reject)

    response = api.post("/admin/allowed_emails", json={"email": OWNER})

    assert response.status_code == 400
    assert "owner access" in response.json()["detail"]


def test_owner_can_remove_an_email(api):
    api_main.app.dependency_overrides[get_current_owner_uid] = lambda: OWNER

    response = api.delete("/admin/allowed_emails/already-allowed@example.com")

    assert response.status_code == 200


def test_owner_can_read_usage_across_every_allowed_user(api, monkeypatch):
    api_main.app.dependency_overrides[get_current_owner_uid] = lambda: OWNER
    seen = {}

    def fake_get_usage_for(emails):
        seen["emails"] = emails
        return [{"email": e, "count": 3} for e in sorted(emails)]

    monkeypatch.setattr(admin, "get_usage_for", fake_get_usage_for)
    monkeypatch.setattr(admin, "get_global_today_count", lambda: 7)
    monkeypatch.setattr(admin, "GLOBAL_DAILY_MESSAGE_LIMIT", 1000)

    response = api.get("/admin/usage")

    assert response.status_code == 200
    assert response.json() == {
        "users": [{"email": "already-allowed@example.com", "count": 3}, {"email": OWNER, "count": 3}],
        "global": {"count": 7, "limit": 1000},
    }
    # The owner is included even though it isn't in the "extra" list.
    assert set(seen["emails"]) == {OWNER, "already-allowed@example.com"}


def test_non_owner_cannot_read_usage(api):
    api_main.app.dependency_overrides[get_current_owner_uid] = lambda: NON_OWNER

    assert api.get("/admin/usage").status_code == 403
