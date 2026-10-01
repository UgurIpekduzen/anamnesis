"""Integration tests for per-user GitHub token storage and encryption
against a real Firestore emulator."""

import uuid

import pytest
from cryptography.fernet import Fernet

from src.integrations.github import connections as github_connections
from src.core.firestore_client import get_client
from src.integrations.github.connections import (
    delete_github_connection,
    get_decrypted_token,
    has_github_connection,
    save_github_token,
)
from src.core.token_encryption import _get_fernet


@pytest.fixture(autouse=True)
def fresh_key(monkeypatch):
    """Set a freshly generated Fernet key as the GitHub token encryption key
    and clear the cached Fernet instance before and after the test."""
    # Independent of whatever real key is in the developer's local .env —
    # tests should pass the same way regardless of that.
    monkeypatch.setenv("GITHUB_TOKEN_ENCRYPTION_KEY", Fernet.generate_key().decode())
    _get_fernet.cache_clear()
    yield
    _get_fernet.cache_clear()


@pytest.fixture
def owner():
    """Generate a fresh owner uid and yield it, deleting its GitHub
    connection document afterwards."""
    owner_uid = f"github-conn-{uuid.uuid4().hex[:8]}@example.com"
    yield owner_uid
    get_client().collection(github_connections.COLLECTION).document(owner_uid).delete()


def test_an_unconnected_user_has_no_connection(owner):
    """A user who never saved a GitHub token has no connection and no
    decrypted token."""
    assert has_github_connection(owner) is False
    assert get_decrypted_token(owner) is None


def test_a_saved_token_round_trips_through_firestore(owner):
    """A token saved with save_github_token is readable back unchanged via
    get_decrypted_token, and has_github_connection reports True."""
    save_github_token(owner, "ghp_exampleTokenValue1234567890")

    assert has_github_connection(owner) is True
    assert get_decrypted_token(owner) == "ghp_exampleTokenValue1234567890"


def test_the_stored_document_never_holds_the_raw_token(owner):
    """The Firestore document written by save_github_token never contains
    the plaintext token, only its encrypted form."""
    save_github_token(owner, "ghp_exampleTokenValue1234567890")

    doc = get_client().collection(github_connections.COLLECTION).document(owner).get().to_dict()
    assert "ghp_exampleTokenValue1234567890" not in str(doc)


def test_saving_again_replaces_the_previous_token(owner):
    """Saving a second token for the same user replaces the first, so
    get_decrypted_token returns only the newest one."""
    save_github_token(owner, "ghp_first")
    save_github_token(owner, "ghp_second")

    assert get_decrypted_token(owner) == "ghp_second"


def test_deleting_removes_the_connection(owner):
    """delete_github_connection removes the saved token so the user has no
    connection and no decrypted token afterwards."""
    save_github_token(owner, "ghp_exampleTokenValue1234567890")

    delete_github_connection(owner)

    assert has_github_connection(owner) is False
    assert get_decrypted_token(owner) is None


def test_one_users_token_does_not_leak_to_another(owner):
    """Saving a token for one user doesn't create a connection for a
    different, unrelated user."""
    other = f"other-{uuid.uuid4().hex[:8]}@example.com"
    try:
        save_github_token(owner, "ghp_exampleTokenValue1234567890")
        assert has_github_connection(other) is False
    finally:
        get_client().collection(github_connections.COLLECTION).document(other).delete()
