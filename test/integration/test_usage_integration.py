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
