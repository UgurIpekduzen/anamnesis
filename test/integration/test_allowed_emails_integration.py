import uuid
from datetime import datetime, timezone

import pytest

from src.accounts import allowed_emails
from src.accounts.allowed_emails import (
    add_allowed_email,
    get_extra_allowed_emails,
    get_invited_ats,
    get_role,
    remove_allowed_email,
    set_role,
)


@pytest.fixture
def email():
    # first.last@ on purpose: a dotted local part, the shape most real emails
    # have — a regression guard against storing roles under a Firestore map
    # key built from the raw address, which "." would silently misparse into
    # a nested path instead of one key (see the module's own comment).
    address = f"first.last-{uuid.uuid4().hex[:8]}@example.com"
    add_allowed_email(address)
    yield address
    remove_allowed_email(address)


def test_a_fresh_allowed_email_is_a_tester_by_default(email):
    assert get_role(email) == "tester"


def test_setting_the_role_to_user_sticks(email):
    set_role(email, "user")

    assert get_role(email) == "user"


def test_setting_it_back_to_tester_sticks(email):
    set_role(email, "user")
    set_role(email, "tester")

    assert get_role(email) == "tester"


def test_the_owner_is_always_admin_regardless_of_any_stored_role(monkeypatch):
    owner = f"owner-{uuid.uuid4().hex[:8]}@example.com"
    monkeypatch.setattr(allowed_emails, "OWNER_EMAILS", {owner})

    assert get_role(owner) == "admin"


def test_setting_a_role_for_the_owner_is_refused(monkeypatch):
    owner = f"owner-{uuid.uuid4().hex[:8]}@example.com"
    monkeypatch.setattr(allowed_emails, "OWNER_EMAILS", {owner})

    with pytest.raises(ValueError):
        set_role(owner, "user")


def test_setting_a_role_for_an_email_not_on_the_allowlist_is_refused():
    with pytest.raises(ValueError):
        set_role(f"unknown-{uuid.uuid4().hex[:8]}@example.com", "user")


def test_an_unrecognized_role_value_is_refused(email):
    with pytest.raises(ValueError):
        set_role(email, "owner")


def test_adding_an_email_records_when_it_was_invited(email):
    before = datetime.now(timezone.utc)

    invited_at = get_invited_ats([email])[email]

    assert abs((invited_at - before).total_seconds()) < 10


def test_an_unknown_email_has_no_invited_at():
    assert get_invited_ats([f"unknown-{uuid.uuid4().hex[:8]}@example.com"]) == {}


def test_removing_an_email_also_clears_its_invited_at():
    address = f"first.last-{uuid.uuid4().hex[:8]}@example.com"
    add_allowed_email(address)

    remove_allowed_email(address)

    assert get_invited_ats([address]) == {}


def test_removing_an_allowed_email_also_resets_its_role():
    address = f"first.last-{uuid.uuid4().hex[:8]}@example.com"
    add_allowed_email(address)
    set_role(address, "user")

    remove_allowed_email(address)

    assert address not in get_extra_allowed_emails(force_refresh=True)
    # Re-adding it later must start as a tester again, not inherit the old role.
    add_allowed_email(address)
    try:
        assert get_role(address) == "tester"
    finally:
        remove_allowed_email(address)
