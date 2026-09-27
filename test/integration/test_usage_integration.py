import uuid

import pytest

from src.accounts import usage
from src.accounts.usage import DailyLimitExceeded, get_today_count, record_message


def test_get_today_count_is_zero_for_an_unseen_owner():
    assert get_today_count(f"unseen-{uuid.uuid4().hex[:8]}@example.com") == 0


def test_record_message_increments_todays_count():
    owner_uid = f"test-owner-{uuid.uuid4().hex[:8]}@example.com"

    assert record_message(owner_uid) == 1
    assert record_message(owner_uid) == 2
    assert record_message(owner_uid) == 3
    assert get_today_count(owner_uid) == 3


def test_record_message_refuses_past_the_hard_limit_without_counting_it(monkeypatch):
    monkeypatch.setattr(usage, "DAILY_MESSAGE_HARD_LIMIT", 3)
    owner_uid = f"test-owner-{uuid.uuid4().hex[:8]}@example.com"

    assert [record_message(owner_uid) for _ in range(3)] == [1, 2, 3]
    with pytest.raises(DailyLimitExceeded) as excinfo:
        record_message(owner_uid)

    assert excinfo.value.limit == 3
    # The refused attempt wasn't counted, so the counter stops at the limit.
    assert get_today_count(owner_uid) == 3


def test_the_hard_limit_starts_over_on_a_new_day(monkeypatch):
    monkeypatch.setattr(usage, "DAILY_MESSAGE_HARD_LIMIT", 1)
    owner_uid = f"test-owner-{uuid.uuid4().hex[:8]}@example.com"
    usage.get_client().collection("usage").document(owner_uid).set({"date": "2000-01-01", "message_count": 99})

    assert record_message(owner_uid) == 1


# APPCE-122: a system-wide ceiling on top of each user's own, so many users
# hitting their own limits on the same day can't run the bill up without end.
def test_record_message_also_counts_toward_the_global_limit(monkeypatch):
    monkeypatch.setattr(usage, "GLOBAL_DAILY_MESSAGE_LIMIT", 1000)
    usage.get_client().collection("usage").document(usage.GLOBAL_USAGE_DOC_ID).delete()
    owner_uid = f"test-owner-{uuid.uuid4().hex[:8]}@example.com"

    record_message(owner_uid)
    record_message(owner_uid)

    assert usage.get_global_today_count() == 2


def test_the_global_limit_refuses_a_message_even_under_the_users_own_limit(monkeypatch):
    monkeypatch.setattr(usage, "GLOBAL_DAILY_MESSAGE_LIMIT", 2)
    usage.get_client().collection("usage").document(usage.GLOBAL_USAGE_DOC_ID).delete()
    first = f"test-owner-{uuid.uuid4().hex[:8]}@example.com"
    second = f"test-owner-{uuid.uuid4().hex[:8]}@example.com"

    record_message(first)
    record_message(second)
    with pytest.raises(DailyLimitExceeded) as excinfo:
        record_message(f"test-owner-{uuid.uuid4().hex[:8]}@example.com")

    assert excinfo.value.limit == 2
    assert excinfo.value.scope == "global"
    # The refused attempt is never counted, on either side.
    assert usage.get_global_today_count() == 2


def test_a_refused_global_attempt_does_not_count_against_the_user_either(monkeypatch):
    monkeypatch.setattr(usage, "GLOBAL_DAILY_MESSAGE_LIMIT", 0)
    usage.get_client().collection("usage").document(usage.GLOBAL_USAGE_DOC_ID).delete()
    owner_uid = f"test-owner-{uuid.uuid4().hex[:8]}@example.com"

    with pytest.raises(DailyLimitExceeded) as excinfo:
        record_message(owner_uid)

    assert excinfo.value.scope == "global"
    assert get_today_count(owner_uid) == 0


def test_the_users_own_limit_is_still_checked_before_the_global_one(monkeypatch):
    monkeypatch.setattr(usage, "DAILY_MESSAGE_HARD_LIMIT", 1)
    monkeypatch.setattr(usage, "GLOBAL_DAILY_MESSAGE_LIMIT", 1000)
    owner_uid = f"test-owner-{uuid.uuid4().hex[:8]}@example.com"

    record_message(owner_uid)
    with pytest.raises(DailyLimitExceeded) as excinfo:
        record_message(owner_uid)

    assert excinfo.value.scope == "user"


def test_the_global_limit_starts_over_on_a_new_day(monkeypatch):
    monkeypatch.setattr(usage, "GLOBAL_DAILY_MESSAGE_LIMIT", 1)
    usage.get_client().collection("usage").document(usage.GLOBAL_USAGE_DOC_ID).set(
        {"date": "2000-01-01", "message_count": 99}
    )

    record_message(f"test-owner-{uuid.uuid4().hex[:8]}@example.com")

    assert usage.get_global_today_count() == 1


def test_get_usage_for_reports_each_emails_own_count_sorted_by_email():
    # Fixed prefixes, not two random ones, so the expected sort order is stable.
    a = f"a-test-owner-{uuid.uuid4().hex[:8]}@example.com"
    b = f"b-test-owner-{uuid.uuid4().hex[:8]}@example.com"
    record_message(a)
    record_message(a)
    record_message(b)

    assert usage.get_usage_for([b, a]) == [{"email": a, "count": 2}, {"email": b, "count": 1}]


def test_get_usage_for_reports_zero_for_an_unseen_email():
    email = f"unseen-{uuid.uuid4().hex[:8]}@example.com"

    assert usage.get_usage_for([email]) == [{"email": email, "count": 0}]


# A lifetime cap for invited (non-owner) testers, independent of the day
# (APPCE-122): the owner is exempt, and it's on top of the daily limits
# above — whichever is hit first refuses the message.
def test_a_tester_is_refused_once_they_reach_the_lifetime_limit(monkeypatch):
    monkeypatch.setattr(usage, "TESTER_LIFETIME_MESSAGE_LIMIT", 2)
    monkeypatch.setattr(usage, "OWNER_EMAILS", {"owner@example.com"})
    tester = f"tester-{uuid.uuid4().hex[:8]}@example.com"

    record_message(tester)
    record_message(tester)
    with pytest.raises(DailyLimitExceeded) as excinfo:
        record_message(tester)

    assert excinfo.value.limit == 2
    assert excinfo.value.scope == "lifetime"


def test_the_lifetime_limit_does_not_apply_to_the_owner(monkeypatch):
    monkeypatch.setattr(usage, "TESTER_LIFETIME_MESSAGE_LIMIT", 1)
    owner = f"owner-{uuid.uuid4().hex[:8]}@example.com"
    monkeypatch.setattr(usage, "OWNER_EMAILS", {owner})

    assert [record_message(owner) for _ in range(3)] == [1, 2, 3]


def test_the_lifetime_limit_does_not_reset_on_a_new_day(monkeypatch):
    monkeypatch.setattr(usage, "TESTER_LIFETIME_MESSAGE_LIMIT", 1)
    monkeypatch.setattr(usage, "OWNER_EMAILS", {"owner@example.com"})
    tester = f"tester-{uuid.uuid4().hex[:8]}@example.com"
    usage.get_client().collection("usage").document(tester).set(
        {"date": "2000-01-01", "message_count": 0, "lifetime_count": 1}
    )

    with pytest.raises(DailyLimitExceeded) as excinfo:
        record_message(tester)

    assert excinfo.value.scope == "lifetime"


def test_a_refused_lifetime_attempt_does_not_inflate_the_days_count(monkeypatch):
    monkeypatch.setattr(usage, "TESTER_LIFETIME_MESSAGE_LIMIT", 0)
    monkeypatch.setattr(usage, "OWNER_EMAILS", {"owner@example.com"})
    tester = f"tester-{uuid.uuid4().hex[:8]}@example.com"

    with pytest.raises(DailyLimitExceeded) as excinfo:
        record_message(tester)

    assert excinfo.value.scope == "lifetime"
    assert get_today_count(tester) == 0
