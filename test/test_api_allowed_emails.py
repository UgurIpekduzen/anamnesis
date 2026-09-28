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
    monkeypatch.setattr(admin, "get_roles", lambda emails: {e: "tester" for e in emails})
    monkeypatch.setattr(admin, "get_names", lambda emails: {})
    monkeypatch.setattr(admin, "add_allowed_email", lambda email: None)
    monkeypatch.setattr(admin, "remove_allowed_email", lambda email: None)
    monkeypatch.setattr(admin, "set_role", lambda email, role: None)
    monkeypatch.setattr(admin, "get_usage_for", lambda emails: [{"email": e, "count": 0, "role": "tester"} for e in sorted(emails)])
    monkeypatch.setattr(admin, "get_global_today_count", lambda: 0)
    monkeypatch.setattr(admin, "GLOBAL_DAILY_MESSAGE_LIMIT", 1000)
    yield TestClient(api_main.app)


def test_owner_can_list_allowed_emails(api):
    api_main.app.dependency_overrides[get_current_owner_uid] = lambda: OWNER

    response = api.get("/admin/allowed_emails")

    assert response.status_code == 200
    assert response.json() == {
        "owner_emails": [OWNER],
        "extra_users": [{"email": "already-allowed@example.com", "role": "tester"}],
        "names": {},
    }


def test_non_owner_is_rejected_from_every_admin_endpoint(api):
    api_main.app.dependency_overrides[get_current_owner_uid] = lambda: NON_OWNER

    assert api.get("/admin/allowed_emails").status_code == 403
    assert api.post("/admin/allowed_emails", json={"email": "x@example.com"}).status_code == 403
    assert api.delete("/admin/allowed_emails/x@example.com").status_code == 403
    assert api.put("/admin/allowed_emails/x@example.com/role", json={"role": "user"}).status_code == 403


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
        return [{"email": e, "count": 3, "role": "tester"} for e in sorted(emails)]

    monkeypatch.setattr(admin, "get_usage_for", fake_get_usage_for)
    monkeypatch.setattr(admin, "get_global_today_count", lambda: 7)
    monkeypatch.setattr(admin, "GLOBAL_DAILY_MESSAGE_LIMIT", 1000)

    response = api.get("/admin/usage")

    assert response.status_code == 200
    assert response.json() == {
        "users": [
            {"email": "already-allowed@example.com", "count": 3, "role": "tester"},
            {"email": OWNER, "count": 3, "role": "tester"},
        ],
        "global": {"count": 7, "limit": 1000},
    }
    # The owner is included even though it isn't in the "extra" list.
    assert set(seen["emails"]) == {OWNER, "already-allowed@example.com"}


def test_non_owner_cannot_read_usage(api):
    api_main.app.dependency_overrides[get_current_owner_uid] = lambda: NON_OWNER

    assert api.get("/admin/usage").status_code == 403


def test_owner_can_set_an_emails_role(api, monkeypatch):
    api_main.app.dependency_overrides[get_current_owner_uid] = lambda: OWNER
    monkeypatch.setattr(admin, "get_roles", lambda emails: {e: "user" for e in emails})

    response = api.put("/admin/allowed_emails/already-allowed@example.com/role", json={"role": "user"})

    assert response.status_code == 200
    assert response.json() == {"extra_users": [{"email": "already-allowed@example.com", "role": "user"}]}


def test_setting_an_ineligible_role_surfaces_the_reason(api, monkeypatch):
    api_main.app.dependency_overrides[get_current_owner_uid] = lambda: OWNER

    def reject(email, role):
        raise ValueError("That email isn't on the allowlist.")

    monkeypatch.setattr(admin, "set_role", reject)

    response = api.put("/admin/allowed_emails/unknown@example.com/role", json={"role": "user"})

    assert response.status_code == 400
    assert "allowlist" in response.json()["detail"]


def test_setting_the_role_back_to_tester(api):
    api_main.app.dependency_overrides[get_current_owner_uid] = lambda: OWNER

    response = api.put("/admin/allowed_emails/already-allowed@example.com/role", json={"role": "tester"})

    assert response.status_code == 200


def test_owner_can_wipe_a_users_data_with_a_matching_confirmation(api, monkeypatch):
    api_main.app.dependency_overrides[get_current_owner_uid] = lambda: OWNER
    seen = {}

    def fake_wipe_user(email, confirm=False):
        seen["email"], seen["confirm"] = email, confirm
        return {"tenants": ["t1"], "github_connection": True, "deleted": True}

    monkeypatch.setattr(admin, "wipe_user", fake_wipe_user)

    response = api.post(
        "/admin/users/already-allowed@example.com/wipe", json={"confirm_email": "already-allowed@example.com"}
    )

    assert response.status_code == 200
    assert seen == {"email": "already-allowed@example.com", "confirm": True}
    body = response.json()
    assert body["deleted"] is True
    assert body["extra_users"] == [{"email": "already-allowed@example.com", "role": "tester"}]


def test_wiping_with_a_mismatched_confirmation_deletes_nothing(api, monkeypatch):
    api_main.app.dependency_overrides[get_current_owner_uid] = lambda: OWNER
    called = []
    monkeypatch.setattr(admin, "wipe_user", lambda email, confirm=False: called.append(email))

    response = api.post("/admin/users/already-allowed@example.com/wipe", json={"confirm_email": "typo@example.com"})

    assert response.status_code == 400
    assert not called


def test_the_owner_cannot_be_wiped(api, monkeypatch):
    api_main.app.dependency_overrides[get_current_owner_uid] = lambda: OWNER

    def reject(email, confirm=False):
        raise ValueError("The owner's data can't be wiped.")

    monkeypatch.setattr(admin, "wipe_user", reject)

    response = api.post("/admin/users/" + OWNER + "/wipe", json={"confirm_email": OWNER})

    assert response.status_code == 400
    assert "owner" in response.json()["detail"]


def test_non_owner_cannot_wipe_anyone(api):
    api_main.app.dependency_overrides[get_current_owner_uid] = lambda: NON_OWNER

    response = api.post(
        "/admin/users/already-allowed@example.com/wipe", json={"confirm_email": "already-allowed@example.com"}
    )

    assert response.status_code == 403
