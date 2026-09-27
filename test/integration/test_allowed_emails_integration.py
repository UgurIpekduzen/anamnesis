import uuid

import pytest

from src.accounts import allowed_emails
from src.accounts.allowed_emails import (
    add_allowed_email,
    get_extra_allowed_emails,
    get_unlimited_emails,
    mark_unlimited,
    remove_allowed_email,
    unmark_unlimited,
)


@pytest.fixture
def email():
    # A random address, so parallel test runs (and reruns) don't collide on
    # the same Firestore array entries.
    address = f"tester-{uuid.uuid4().hex[:8]}@example.com"
    add_allowed_email(address)
    yield address
    remove_allowed_email(address)


def test_marking_an_email_unlimited_adds_it_to_the_set(email):
    mark_unlimited(email)

    assert email in get_unlimited_emails(force_refresh=True)


def test_unmarking_removes_it(email):
    mark_unlimited(email)
    unmark_unlimited(email)

    assert email not in get_unlimited_emails(force_refresh=True)


def test_a_fresh_allowed_email_is_not_unlimited_by_default(email):
    assert email not in get_unlimited_emails(force_refresh=True)


def test_marking_an_email_not_on_the_allowlist_is_refused():
    with pytest.raises(ValueError):
        mark_unlimited(f"unknown-{uuid.uuid4().hex[:8]}@example.com")


def test_the_owner_cannot_be_marked_unlimited(monkeypatch):
    owner = f"owner-{uuid.uuid4().hex[:8]}@example.com"
    monkeypatch.setattr(allowed_emails, "OWNER_EMAILS", {owner})

    with pytest.raises(ValueError):
        mark_unlimited(owner)


def test_removing_an_allowed_email_also_clears_its_unlimited_flag():
    address = f"tester-{uuid.uuid4().hex[:8]}@example.com"
    add_allowed_email(address)
    mark_unlimited(address)

    remove_allowed_email(address)

    assert address not in get_unlimited_emails(force_refresh=True)
    assert address not in get_extra_allowed_emails(force_refresh=True)
