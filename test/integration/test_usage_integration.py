import uuid

from src.usage import get_today_count, record_message


def test_get_today_count_is_zero_for_an_unseen_owner():
    assert get_today_count(f"unseen-{uuid.uuid4().hex[:8]}@example.com") == 0


def test_record_message_increments_todays_count():
    owner_uid = f"test-owner-{uuid.uuid4().hex[:8]}@example.com"

    assert record_message(owner_uid) == 1
    assert record_message(owner_uid) == 2
    assert record_message(owner_uid) == 3
    assert get_today_count(owner_uid) == 3
