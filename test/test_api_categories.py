"""Tests for the GET/PUT/DELETE /categories endpoints."""

import pytest
from starlette.testclient import TestClient

import api.main as api_main
from api.routers import categories

OWNER = "test@example.com"


@pytest.fixture
def api(monkeypatch, signed_in_owner):
    """Patch category storage with an in-memory dict keyed by owner_uid, and yield a (TestClient, stored) pair."""
    stored = {}

    def save(owner_uid, categories):
        """Validate the given category names and store them for owner_uid."""
        from src.facts.categories import check_category_names

        stored[owner_uid] = check_category_names(categories)

    monkeypatch.setattr(categories, "save_categories", save)
    monkeypatch.setattr(
        categories, "reset_categories", lambda owner_uid: stored.pop(owner_uid, None)
    )
    monkeypatch.setattr(
        categories,
        "get_category_settings",
        lambda owner_uid: {
            "categories": stored.get(owner_uid, ["architecture", "note"]),
            "suggested": ["architecture", "note"],
            "customized": owner_uid in stored,
            "max": 12,
        },
    )
    return TestClient(api_main.app), stored


def test_get_returns_the_suggested_list_until_it_is_changed(api):
    """GET /categories returns the suggested list, uncustomized, until the user changes it."""
    client, _ = api

    assert client.get("/categories").json() == {
        "categories": ["architecture", "note"],
        "suggested": ["architecture", "note"],
        "customized": False,
        "max": 12,
    }


def test_put_saves_the_users_own_list_and_returns_it(api):
    """PUT /categories normalizes and saves the user's own list, returning it marked as customized."""
    client, stored = api

    response = client.put("/categories", json={"categories": ["Risk", "note"]})

    assert response.status_code == 200
    assert (
        response.json()["categories"] == ["risk", "note"] and response.json()["customized"] is True
    )
    assert stored == {OWNER: ["risk", "note"]}


def test_delete_goes_back_to_the_suggested_list(api):
    """DELETE /categories clears the user's customized list, reverting to the suggested one."""
    client, stored = api
    client.put("/categories", json={"categories": ["risk"]})

    response = client.delete("/categories")

    assert response.json()["customized"] is False
    assert stored == {}


@pytest.mark.parametrize(
    "body",
    [
        {"categories": []},
        {"categories": ["has space"]},
        {"categories": ["a", "a"]},
        {"categories": ["x"] * 13},
    ],
)
def test_an_invalid_list_is_a_400_with_the_reason_and_nothing_is_saved(api, body):
    """An empty list, a name with a space, duplicate names, or too many names is rejected with a 400 and nothing is saved."""
    client, stored = api

    response = client.put("/categories", json=body)

    assert response.status_code == 400 and response.json()["detail"]
    assert stored == {}


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"categories": "note"},
        {"categories": [1]},
        {"categories": ["a"], "owner_uid": "x"},
        {"categories": ["a"] * 51},
    ],
)
def test_a_malformed_body_is_a_422(api, body):
    """A missing field, wrong-typed categories, an unknown extra field, or an oversized list is rejected with a 422."""
    client, stored = api

    assert client.put("/categories", json=body).status_code == 422
    assert stored == {}


def test_the_category_endpoints_require_authentication():
    """GET, PUT, and DELETE /categories all return 401 without an authenticated user."""
    client = TestClient(api_main.app)

    assert client.get("/categories").status_code == 401
    assert client.put("/categories", json={"categories": ["a"]}).status_code == 401
    assert client.delete("/categories").status_code == 401
