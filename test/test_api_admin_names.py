import pytest
from starlette.testclient import TestClient

import api.main as api_main
from api.deps import get_current_owner_uid
from api.routers import admin

OWNER = "test@example.com"
NON_OWNER = "someone-else@example.com"
TARGET = "already-allowed@example.com"


@pytest.fixture
def api(monkeypatch):
    monkeypatch.setattr(admin, "get_extra_allowed_emails", lambda: {TARGET})
    monkeypatch.setattr(admin, "set_name", lambda email, name: name.strip() or None)
    yield TestClient(api_main.app)


def test_owner_can_set_a_users_name(api):
    api_main.app.dependency_overrides[get_current_owner_uid] = lambda: OWNER

    response = api.put(f"/admin/users/{TARGET}/name", json={"name": "Ada Lovelace"})

    assert response.status_code == 200
    assert response.json() == {"email": TARGET, "name": "Ada Lovelace"}


def test_an_empty_name_clears_it(api):
    api_main.app.dependency_overrides[get_current_owner_uid] = lambda: OWNER

    response = api.put(f"/admin/users/{TARGET}/name", json={"name": "  "})

    assert response.status_code == 200
    assert response.json() == {"email": TARGET, "name": None}


def test_owner_can_set_their_own_name_too(api):
    # Unlike role/wipe, there's no lockout risk in a display name — the
    # owner isn't excluded from being a target (APPCE-126).
    api_main.app.dependency_overrides[get_current_owner_uid] = lambda: OWNER

    response = api.put(f"/admin/users/{OWNER}/name", json={"name": "The Owner"})

    assert response.status_code == 200


def test_a_name_for_an_unknown_email_is_refused(api):
    api_main.app.dependency_overrides[get_current_owner_uid] = lambda: OWNER

    response = api.put("/admin/users/unknown@example.com/name", json={"name": "Nobody"})

    assert response.status_code == 400
    assert "allowlist" in response.json()["detail"]


def test_non_owner_cannot_set_anyones_name(api):
    api_main.app.dependency_overrides[get_current_owner_uid] = lambda: NON_OWNER

    response = api.put(f"/admin/users/{TARGET}/name", json={"name": "Ada Lovelace"})

    assert response.status_code == 403


def test_a_name_over_the_length_limit_is_rejected(api):
    api_main.app.dependency_overrides[get_current_owner_uid] = lambda: OWNER

    response = api.put(f"/admin/users/{TARGET}/name", json={"name": "x" * 101})

    assert response.status_code == 422


def test_extra_fields_are_rejected(api):
    api_main.app.dependency_overrides[get_current_owner_uid] = lambda: OWNER

    response = api.put(f"/admin/users/{TARGET}/name", json={"name": "Ada Lovelace", "email": "sneaky@example.com"})

    assert response.status_code == 422
