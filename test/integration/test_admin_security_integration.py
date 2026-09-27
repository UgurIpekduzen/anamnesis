"""Security checks for the admin/usage additions (APPCE-122): the messaging
ceilings are only worth building if they hold under real concurrency, and the
owner-only endpoints are only safe if they refuse a non-owner and reject a
malformed request before touching data. These run against the real router and
the real src functions (no monkeypatching), so a wiring mistake between them
would show up here even if a unit test with mocks stays green.
"""

import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest
from starlette.testclient import TestClient

import api.deps
import api.main as api_main
from api.deps import get_current_owner_uid
from src.accounts import allowed_emails, usage
from src.accounts.allowed_emails import add_allowed_email, remove_allowed_email
from src.accounts.usage import DailyLimitExceeded, get_global_today_count, get_today_count, record_message

NON_OWNER = "someone-else@example.com"


@pytest.fixture(autouse=True)
def _reset_overrides():
    yield
    api_main.app.dependency_overrides.clear()


# --- Concurrency: do the ceilings actually hold under real contention? ------
#
# record_message's guarantee only means something if two requests arriving at
# the same instant can't both slip under a limit — a race here would quietly
# defeat the whole point of APPCE-122's cost protection.


def _attempt(owner_uid):
    """Call record_message once, folding "refused" and "the transaction
    couldn't commit under contention" (a real, expected outcome under heavy
    concurrency — see chat.py's fail-open comment) into one "didn't count"
    result, distinct from a real count."""
    try:
        return record_message(owner_uid)
    except DailyLimitExceeded:
        return None
    except ValueError:
        return None


def test_concurrent_messages_never_push_a_user_past_their_own_limit(monkeypatch):
    monkeypatch.setattr(usage, "DAILY_MESSAGE_HARD_LIMIT", 5)
    monkeypatch.setattr(usage, "GLOBAL_DAILY_MESSAGE_LIMIT", 1000)
    monkeypatch.setattr(usage, "OWNER_EMAILS", {"owner@example.com"})
    owner_uid = f"tester-{uuid.uuid4().hex[:8]}@example.com"

    # 2x over-subscribed, not 4x — enough to exercise the race without
    # exhausting the emulator's own transaction-retry budget, which would
    # fail some attempts for an unrelated reason (see _attempt).
    with ThreadPoolExecutor(max_workers=10) as pool:
        results = list(pool.map(_attempt, [owner_uid] * 10))

    succeeded = [r for r in results if r is not None]
    # The property this test exists to prove: whatever the mix of successes
    # and failures, the persisted count is never more than the limit — never
    # a duplicate, never one over.
    assert len(succeeded) == len(set(succeeded)) <= 5
    assert get_today_count(owner_uid) == len(succeeded)


def test_concurrent_messages_never_push_the_global_count_past_its_limit(monkeypatch):
    monkeypatch.setattr(usage, "DAILY_MESSAGE_HARD_LIMIT", 1000)
    monkeypatch.setattr(usage, "GLOBAL_DAILY_MESSAGE_LIMIT", 5)
    monkeypatch.setattr(usage, "OWNER_EMAILS", {"owner@example.com"})
    usage.get_client().collection("usage").document(usage.GLOBAL_USAGE_DOC_ID).delete()

    with ThreadPoolExecutor(max_workers=10) as pool:
        results = list(pool.map(_attempt, [f"tester-{uuid.uuid4().hex[:8]}@example.com" for _ in range(10)]))

    succeeded = sum(1 for r in results if r is not None)
    assert succeeded <= 5
    assert get_global_today_count() == succeeded


def test_concurrent_messages_never_push_a_tester_past_their_lifetime_cap(monkeypatch):
    monkeypatch.setattr(usage, "TESTER_LIFETIME_MESSAGE_LIMIT", 5)
    monkeypatch.setattr(usage, "DAILY_MESSAGE_HARD_LIMIT", 1000)
    monkeypatch.setattr(usage, "GLOBAL_DAILY_MESSAGE_LIMIT", 1000)
    monkeypatch.setattr(usage, "OWNER_EMAILS", {"owner@example.com"})
    tester = f"tester-{uuid.uuid4().hex[:8]}@example.com"

    with ThreadPoolExecutor(max_workers=10) as pool:
        results = list(pool.map(_attempt, [tester] * 10))

    succeeded = sum(1 for r in results if r is not None)
    assert succeeded <= 5


# --- Full stack, unmocked: does the router really enforce what the unit
# tests (with the functions monkeypatched) assume it does? --------------------


def test_a_non_owner_is_refused_before_any_data_is_touched():
    # No emulator env needed for this one: require_owner rejects the caller
    # from the token's claims alone, before any src function runs.
    api_main.app.dependency_overrides[get_current_owner_uid] = lambda: NON_OWNER
    client = TestClient(api_main.app)

    assert client.get("/admin/usage").status_code == 403
    assert client.get("/admin/allowed_emails").status_code == 403
    assert client.post("/admin/allowed_emails/x@example.com/unlimited").status_code == 403
    assert client.delete("/admin/allowed_emails/x@example.com/unlimited").status_code == 403


def test_the_owner_is_really_refused_from_marking_themselves_unlimited(monkeypatch):
    owner = f"owner-{uuid.uuid4().hex[:8]}@example.com"
    monkeypatch.setattr(allowed_emails, "OWNER_EMAILS", {owner})
    monkeypatch.setattr(api.deps, "OWNER_EMAILS", {owner})
    api_main.app.dependency_overrides[get_current_owner_uid] = lambda: owner
    client = TestClient(api_main.app)

    response = client.post(f"/admin/allowed_emails/{owner}/unlimited")

    assert response.status_code == 400
    assert owner not in allowed_emails.get_unlimited_emails(force_refresh=True)


def test_an_email_not_on_the_allowlist_is_really_refused(monkeypatch):
    owner = f"owner-{uuid.uuid4().hex[:8]}@example.com"
    monkeypatch.setattr(allowed_emails, "OWNER_EMAILS", {owner})
    monkeypatch.setattr(api.deps, "OWNER_EMAILS", {owner})
    api_main.app.dependency_overrides[get_current_owner_uid] = lambda: owner
    client = TestClient(api_main.app)
    unknown = f"unknown-{uuid.uuid4().hex[:8]}@example.com"

    response = client.post(f"/admin/allowed_emails/{unknown}/unlimited")

    assert response.status_code == 400
    assert unknown not in allowed_emails.get_unlimited_emails(force_refresh=True)


def test_marking_unlimited_end_to_end_actually_exempts_the_email(monkeypatch):
    owner = f"owner-{uuid.uuid4().hex[:8]}@example.com"
    monkeypatch.setattr(allowed_emails, "OWNER_EMAILS", {owner})
    monkeypatch.setattr(api.deps, "OWNER_EMAILS", {owner})
    monkeypatch.setattr(usage, "OWNER_EMAILS", {owner})
    monkeypatch.setattr(usage, "TESTER_LIFETIME_MESSAGE_LIMIT", 1)
    api_main.app.dependency_overrides[get_current_owner_uid] = lambda: owner
    client = TestClient(api_main.app)
    tester = f"tester-{uuid.uuid4().hex[:8]}@example.com"
    add_allowed_email(tester)
    try:
        response = client.post(f"/admin/allowed_emails/{tester}/unlimited")
        assert response.status_code == 200

        assert [record_message(tester) for _ in range(3)] == [1, 2, 3]
    finally:
        remove_allowed_email(tester)


# --- Can't sneak extra fields into the allowlist write ----------------------


def test_extra_fields_on_the_allowed_email_body_are_rejected(monkeypatch):
    monkeypatch.setattr(api.deps, "OWNER_EMAILS", {"owner@example.com"})
    api_main.app.dependency_overrides[get_current_owner_uid] = lambda: "owner@example.com"
    client = TestClient(api_main.app)

    response = client.post(
        "/admin/allowed_emails", json={"email": "x@example.com", "unlimited_emails": ["x@example.com"]}
    )

    assert response.status_code == 422
