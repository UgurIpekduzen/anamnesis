import pytest
from starlette.testclient import TestClient

import api.main as api_main
from api.deps import get_current_owner_uid
from api.routers import admin

OWNER = "test@example.com"
NON_OWNER = "someone-else@example.com"
ALICE = "alice@example.com"
BOB = "bob@example.com"


@pytest.fixture
def api(monkeypatch):
    monkeypatch.setattr(admin, "get_extra_allowed_emails", lambda: {ALICE, BOB})
    monkeypatch.setattr(admin, "get_roles", lambda emails: {e: "tester" for e in emails})
    monkeypatch.setattr(admin, "get_names", lambda emails: {ALICE: "Ada Lovelace"})
    monkeypatch.setattr(
        admin, "get_usage_for", lambda emails: [{"email": e, "count": 3, "role": "tester"} for e in sorted(emails)]
    )
    monkeypatch.setattr(admin, "get_global_today_count", lambda: 7)
    monkeypatch.setattr(admin, "GLOBAL_DAILY_MESSAGE_LIMIT", 1000)
    yield TestClient(api_main.app)


def test_owner_can_list_users(api):
    api_main.app.dependency_overrides[get_current_owner_uid] = lambda: OWNER

    response = api.get("/admin/users")

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 3
    assert body["global"] == {"count": 7, "limit": 1000}
    emails = [u["email"] for u in body["users"]]
    assert emails == sorted([OWNER, ALICE, BOB])
    ada = next(u for u in body["users"] if u["email"] == ALICE)
    assert ada == {"email": ALICE, "role": "tester", "name": "Ada Lovelace", "count": 3}
    bob = next(u for u in body["users"] if u["email"] == BOB)
    assert bob["name"] is None


def test_search_matches_name_case_insensitively(api):
    api_main.app.dependency_overrides[get_current_owner_uid] = lambda: OWNER

    response = api.get("/admin/users", params={"q": "lovelace"})

    body = response.json()
    assert [u["email"] for u in body["users"]] == [ALICE]
    assert body["total"] == 1


def test_search_matches_email_when_no_name_is_set(api):
    api_main.app.dependency_overrides[get_current_owner_uid] = lambda: OWNER

    response = api.get("/admin/users", params={"q": "bob@"})

    assert [u["email"] for u in response.json()["users"]] == [BOB]


def test_search_with_no_match_returns_an_empty_list(api):
    api_main.app.dependency_overrides[get_current_owner_uid] = lambda: OWNER

    response = api.get("/admin/users", params={"q": "nobody"})

    assert response.json() == {
        "users": [],
        "total": 0,
        "limit": 50,
        "offset": 0,
        "global": {"count": 7, "limit": 1000},
    }


def test_limit_and_offset_page_through_the_results(api):
    api_main.app.dependency_overrides[get_current_owner_uid] = lambda: OWNER

    first_page = api.get("/admin/users", params={"limit": 2, "offset": 0}).json()
    second_page = api.get("/admin/users", params={"limit": 2, "offset": 2}).json()

    assert len(first_page["users"]) == 2
    assert first_page["total"] == 3
    assert len(second_page["users"]) == 1
    assert [u["email"] for u in first_page["users"] + second_page["users"]] == sorted([OWNER, ALICE, BOB])


def test_non_owner_cannot_list_users(api):
    api_main.app.dependency_overrides[get_current_owner_uid] = lambda: NON_OWNER

    assert api.get("/admin/users").status_code == 403


@pytest.mark.parametrize("params", [{"limit": 0}, {"limit": 201}, {"offset": -1}])
def test_out_of_range_paging_params_are_rejected(api, params):
    api_main.app.dependency_overrides[get_current_owner_uid] = lambda: OWNER

    assert api.get("/admin/users", params=params).status_code == 422
