"""Integration tests for storing, reading, and deleting Jira credentials in Firestore."""

import uuid

import pytest
from cryptography.fernet import Fernet

from src.integrations.jira import connections as jira_connections
from src.core.firestore_client import get_client
from src.integrations.jira.connections import (
    delete_jira_connection,
    get_jira_base_url,
    get_jira_credentials,
    has_jira_connection,
    save_jira_credentials,
)
from src.core.token_encryption import _get_fernet


@pytest.fixture(autouse=True)
def fresh_key(monkeypatch):
    """Set a freshly generated encryption key for the test and clear the cached Fernet before and after."""
    # Independent of whatever real key is in the developer's local .env —
    # tests should pass the same way regardless of that.
    monkeypatch.setenv("GITHUB_TOKEN_ENCRYPTION_KEY", Fernet.generate_key().decode())
    _get_fernet.cache_clear()
    yield
    _get_fernet.cache_clear()


@pytest.fixture
def owner():
    """Yield a unique owner UID and delete its Jira connection document afterwards."""
    owner_uid = f"jira-conn-{uuid.uuid4().hex[:8]}@example.com"
    yield owner_uid
    get_client().collection(jira_connections.COLLECTION).document(owner_uid).delete()


def test_an_unconnected_user_has_no_connection(owner):
    """A user with no saved Jira credentials has no connection and no credentials."""
    assert has_jira_connection(owner) is False
    assert get_jira_credentials(owner) is None


def test_saved_credentials_round_trip_through_firestore(owner):
    """Credentials saved to Firestore are read back unchanged."""
    save_jira_credentials(owner, "user@example.com", "secret-token", "https://example.atlassian.net")

    assert has_jira_connection(owner) is True
    assert get_jira_credentials(owner) == {
        "email": "user@example.com",
        "token": "secret-token",
        "base_url": "https://example.atlassian.net",
    }


def test_the_base_url_is_stored_without_a_trailing_slash(owner):
    """A base URL saved with a trailing slash is stored without it."""
    save_jira_credentials(owner, "user@example.com", "secret-token", "https://example.atlassian.net/")

    assert get_jira_credentials(owner)["base_url"] == "https://example.atlassian.net"


def test_the_base_url_can_be_read_without_the_encryption_key(owner, monkeypatch):
    """The base URL can be read even when the token encryption key is unset."""
    save_jira_credentials(owner, "user@example.com", "secret-token", "https://example.atlassian.net/")

    # No key at all: reading the address must not need one.
    monkeypatch.delenv("GITHUB_TOKEN_ENCRYPTION_KEY")
    _get_fernet.cache_clear()

    assert get_jira_base_url(owner) == "https://example.atlassian.net"


def test_an_unconnected_user_has_no_base_url(owner):
    """A user with no saved Jira credentials has no base URL."""
    assert get_jira_base_url(owner) is None


def test_the_stored_document_never_holds_the_raw_token(owner):
    """The raw token string never appears in the stored Firestore document."""
    save_jira_credentials(owner, "user@example.com", "secret-token", "https://example.atlassian.net")

    doc = get_client().collection(jira_connections.COLLECTION).document(owner).get().to_dict()
    assert "secret-token" not in str(doc)


def test_saving_again_replaces_the_previous_credentials(owner):
    """Saving credentials again replaces the previously saved ones entirely."""
    save_jira_credentials(owner, "first@example.com", "first-token", "https://first.atlassian.net")
    save_jira_credentials(owner, "second@example.com", "second-token", "https://second.atlassian.net")

    assert get_jira_credentials(owner) == {
        "email": "second@example.com",
        "token": "second-token",
        "base_url": "https://second.atlassian.net",
    }


def test_deleting_removes_the_connection(owner):
    """Deleting a saved connection removes it, leaving the user with no connection or credentials."""
    save_jira_credentials(owner, "user@example.com", "secret-token", "https://example.atlassian.net")

    delete_jira_connection(owner)

    assert has_jira_connection(owner) is False
    assert get_jira_credentials(owner) is None


def test_one_users_credentials_do_not_leak_to_another(owner):
    """Saving one user's Jira credentials does not create a connection for another user."""
    other = f"other-{uuid.uuid4().hex[:8]}@example.com"
    try:
        save_jira_credentials(owner, "user@example.com", "secret-token", "https://example.atlassian.net")
        assert has_jira_connection(other) is False
    finally:
        get_client().collection(jira_connections.COLLECTION).document(other).delete()
