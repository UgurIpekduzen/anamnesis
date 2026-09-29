"""Integration tests for reading and writing user display names against Firestore."""

import uuid

import pytest

from src.accounts.profiles import MAX_NAME_LENGTH, get_name, get_names, set_name


@pytest.fixture
def email():
    """Yield a unique email address for a test and clear its saved name afterwards."""
    email = f"profile-{uuid.uuid4().hex[:8]}@example.com"
    yield email
    set_name(email, "")


def test_an_unseen_email_has_no_name(email):
    """An email with no saved name returns None."""
    assert get_name(email) is None


def test_a_set_name_is_read_back(email):
    """A name saved for an email is read back unchanged."""
    set_name(email, "Ada Lovelace")

    assert get_name(email) == "Ada Lovelace"


def test_a_name_is_trimmed(email):
    """A name saved with surrounding whitespace is stored and read back trimmed."""
    set_name(email, "  Ada Lovelace  ")

    assert get_name(email) == "Ada Lovelace"


def test_setting_an_empty_name_clears_it(email):
    """Setting an empty name clears a previously saved name."""
    set_name(email, "Ada Lovelace")

    set_name(email, "")

    assert get_name(email) is None


def test_setting_a_whitespace_only_name_clears_it(email):
    """Setting a whitespace-only name clears a previously saved name."""
    set_name(email, "Ada Lovelace")

    set_name(email, "   ")

    assert get_name(email) is None


def test_a_name_over_the_length_limit_is_rejected(email):
    """Setting a name longer than the maximum length raises ValueError and saves nothing."""
    with pytest.raises(ValueError):
        set_name(email, "x" * (MAX_NAME_LENGTH + 1))

    assert get_name(email) is None


def test_get_names_batches_several_emails(email):
    """Batch-fetching names for several emails returns each saved name and omits unset ones."""
    other = f"profile-{uuid.uuid4().hex[:8]}@example.com"
    unset = f"profile-{uuid.uuid4().hex[:8]}@example.com"
    set_name(email, "Ada Lovelace")
    set_name(other, "Grace Hopper")
    try:
        assert get_names([email, other, unset]) == {email: "Ada Lovelace", other: "Grace Hopper"}
    finally:
        set_name(other, "")
