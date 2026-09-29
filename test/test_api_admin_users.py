from datetime import datetime, timezone

import pytest
from starlette.testclient import TestClient

import api.main as api_main
from api.deps import get_current_owner_uid
from api.routers import admin

OWNER = "test@example.com"
NON_OWNER = "someone-else@example.com"
ALICE = "alice@example.com"
BOB = "bob@example.com"

ALICE_INVITED_AT = datetime(2026, 1, 1, tzinfo=timezone.utc)
BOB_INVITED_AT = datetime(2026, 6, 1, tzinfo=timezone.utc)


@pytest.fixture
def api(monkeypatch):
    monkeypatch.setattr(admin, "get_extra_allowed_emails", lambda: {ALICE, BOB})
    monkeypatch.setattr(admin, "get_roles", lambda emails: {e: "tester" for e in emails})
    monkeypatch.setattr(admin, "get_names", lambda emails: {ALICE: "Ada Lovelace"})
    monkeypatch.setattr(
        admin, "get_usage_for", lambda emails: [{"email": e, "count": 3, "role": "tester"} for e in sorted(emails)]
    )
    # Alice invited before Bob; the owner has no record (came from Terraform,
    # not this flow) and so sorts before both.
    monkeypatch.setattr(admin, "get_invited_ats", lambda emails: {ALICE: ALICE_INVITED_AT, BOB: BOB_INVITED_AT})
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
    # Oldest invite first, owner (no invite record) first of all.
    assert [u["email"] for u in body["users"]] == [OWNER, ALICE, BOB]
    ada = next(u for u in body["users"] if u["email"] == ALICE)
    assert ada == {
        "email": ALICE,
        "role": "tester",
        "name": "Ada Lovelace",
        "count": 3,
        "invited_at": ALICE_INVITED_AT.isoformat(),
    }
    owner = next(u for u in body["users"] if u["email"] == OWNER)
    assert owner["invited_at"] is None
    bob = next(u for u in body["users"] if u["email"] == BOB)
    assert bob["name"] is None


def test_a_newly_invited_email_sorts_last(api, monkeypatch):
    # Simulates add_allowed_email having just run for a brand new email.
    newest = datetime(2026, 9, 29, tzinfo=timezone.utc)
    monkeypatch.setattr(admin, "get_extra_allowed_emails", lambda: {ALICE, BOB, "carol@example.com"})
    monkeypatch.setattr(
        admin,
        "get_invited_ats",
        lambda emails: {ALICE: ALICE_INVITED_AT, BOB: BOB_INVITED_AT, "carol@example.com": newest},
    )
    api_main.app.dependency_overrides[get_current_owner_uid] = lambda: OWNER

    response = api.get("/admin/users")

    assert [u["email"] for u in response.json()["users"]] == [OWNER, ALICE, BOB, "carol@example.com"]


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
    assert [u["email"] for u in first_page["users"] + second_page["users"]] == [OWNER, ALICE, BOB]


def test_non_owner_cannot_list_users(api):
    api_main.app.dependency_overrides[get_current_owner_uid] = lambda: NON_OWNER

    assert api.get("/admin/users").status_code == 403


@pytest.mark.parametrize("params", [{"limit": 0}, {"limit": 201}, {"offset": -1}])
def test_out_of_range_paging_params_are_rejected(api, params):
    api_main.app.dependency_overrides[get_current_owner_uid] = lambda: OWNER

    assert api.get("/admin/users", params=params).status_code == 422
