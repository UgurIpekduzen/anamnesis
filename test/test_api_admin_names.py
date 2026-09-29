"""Tests for the PUT /admin/users/{email}/name endpoint."""

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
    """Patch the allowlist to just TARGET and set_name to strip/blank-to-None, and yield a TestClient for api.main.app."""
    monkeypatch.setattr(admin, "get_extra_allowed_emails", lambda: {TARGET})
    monkeypatch.setattr(admin, "set_name", lambda email, name: name.strip() or None)
    yield TestClient(api_main.app)


def test_owner_can_set_a_users_name(api):
    """The owner can PUT a display name for an allowed email."""
    api_main.app.dependency_overrides[get_current_owner_uid] = lambda: OWNER

    response = api.put(f"/admin/users/{TARGET}/name", json={"name": "Ada Lovelace"})

    assert response.status_code == 200
    assert response.json() == {"email": TARGET, "name": "Ada Lovelace"}


def test_an_empty_name_clears_it(api):
    """Setting a whitespace-only name clears it back to null."""
    api_main.app.dependency_overrides[get_current_owner_uid] = lambda: OWNER

    response = api.put(f"/admin/users/{TARGET}/name", json={"name": "  "})

    assert response.status_code == 200
    assert response.json() == {"email": TARGET, "name": None}


def test_owner_can_set_their_own_name_too(api):
    """The owner can also set their own display name; unlike role/wipe, they aren't excluded as a target."""
    # Unlike role/wipe, there's no lockout risk in a display name — the
    # owner isn't excluded from being a target.
    api_main.app.dependency_overrides[get_current_owner_uid] = lambda: OWNER

    response = api.put(f"/admin/users/{OWNER}/name", json={"name": "The Owner"})

    assert response.status_code == 200


def test_a_name_for_an_unknown_email_is_refused(api):
    """Setting a name for an email that isn't on the allowlist is refused with a 400 mentioning the allowlist."""
    api_main.app.dependency_overrides[get_current_owner_uid] = lambda: OWNER

    response = api.put("/admin/users/unknown@example.com/name", json={"name": "Nobody"})

    assert response.status_code == 400
    assert "allowlist" in response.json()["detail"]


def test_non_owner_cannot_set_anyones_name(api):
    """A non-owner gets a 403 when trying to set anyone's name."""
    api_main.app.dependency_overrides[get_current_owner_uid] = lambda: NON_OWNER

    response = api.put(f"/admin/users/{TARGET}/name", json={"name": "Ada Lovelace"})

    assert response.status_code == 403


def test_a_name_over_the_length_limit_is_rejected(api):
    """A name longer than the length limit is rejected with a 422."""
    api_main.app.dependency_overrides[get_current_owner_uid] = lambda: OWNER

    response = api.put(f"/admin/users/{TARGET}/name", json={"name": "x" * 101})

    assert response.status_code == 422


def test_extra_fields_are_rejected(api):
    """An unexpected extra field (like an email) in the request body is rejected with a 422."""
    api_main.app.dependency_overrides[get_current_owner_uid] = lambda: OWNER

    response = api.put(f"/admin/users/{TARGET}/name", json={"name": "Ada Lovelace", "email": "sneaky@example.com"})

    assert response.status_code == 422
