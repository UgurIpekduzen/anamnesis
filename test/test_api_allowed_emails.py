import os

# api.deps and src.allowed_emails both read these at import time — kept in
# sync with the convention every other test_api_*.py file already uses, or
# whichever one gets imported first during test collection wins for the
# whole session (module-level constants aren't re-evaluated per test).
os.environ.setdefault("GOOGLE_OAUTH_CLIENT_ID", "test-client-id")
os.environ.setdefault("ALLOWED_EMAILS", "test@example.com")

import pytest  # noqa: E402
from starlette.testclient import TestClient  # noqa: E402

import api.main as api_main  # noqa: E402
from api.deps import get_current_owner_uid  # noqa: E402

OWNER = "test@example.com"
NON_OWNER = "someone-else@example.com"


@pytest.fixture
def api(monkeypatch):
    monkeypatch.setattr(api_main, "get_extra_allowed_emails", lambda: {"already-allowed@example.com"})
    monkeypatch.setattr(api_main, "add_allowed_email", lambda email: None)
    monkeypatch.setattr(api_main, "remove_allowed_email", lambda email: None)
    yield TestClient(api_main.app)
    api_main.app.dependency_overrides.clear()


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

    monkeypatch.setattr(api_main, "add_allowed_email", reject)

    response = api.post("/admin/allowed_emails", json={"email": OWNER})

    assert response.status_code == 400
    assert "owner access" in response.json()["detail"]


def test_owner_can_remove_an_email(api):
    api_main.app.dependency_overrides[get_current_owner_uid] = lambda: OWNER

    response = api.delete("/admin/allowed_emails/already-allowed@example.com")

    assert response.status_code == 200
