import uuid

import pytest

from src.accounts.profiles import MAX_NAME_LENGTH, get_name, get_names, set_name


@pytest.fixture
def email():
    email = f"profile-{uuid.uuid4().hex[:8]}@example.com"
    yield email
    set_name(email, "")


def test_an_unseen_email_has_no_name(email):
    assert get_name(email) is None


def test_a_set_name_is_read_back(email):
    set_name(email, "Ada Lovelace")

    assert get_name(email) == "Ada Lovelace"


def test_a_name_is_trimmed(email):
    set_name(email, "  Ada Lovelace  ")

    assert get_name(email) == "Ada Lovelace"


def test_setting_an_empty_name_clears_it(email):
    set_name(email, "Ada Lovelace")

    set_name(email, "")

    assert get_name(email) is None


def test_setting_a_whitespace_only_name_clears_it(email):
    set_name(email, "Ada Lovelace")

    set_name(email, "   ")

    assert get_name(email) is None


def test_a_name_over_the_length_limit_is_rejected(email):
    with pytest.raises(ValueError):
        set_name(email, "x" * (MAX_NAME_LENGTH + 1))

    assert get_name(email) is None


def test_get_names_batches_several_emails(email):
    other = f"profile-{uuid.uuid4().hex[:8]}@example.com"
    unset = f"profile-{uuid.uuid4().hex[:8]}@example.com"
    set_name(email, "Ada Lovelace")
    set_name(other, "Grace Hopper")
    try:
        assert get_names([email, other, unset]) == {email: "Ada Lovelace", other: "Grace Hopper"}
    finally:
        set_name(other, "")
