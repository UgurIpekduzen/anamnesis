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
    # Independent of whatever real key is in the developer's local .env —
    # tests should pass the same way regardless of that.
    monkeypatch.setenv("GITHUB_TOKEN_ENCRYPTION_KEY", Fernet.generate_key().decode())
    _get_fernet.cache_clear()
    yield
    _get_fernet.cache_clear()


@pytest.fixture
def owner():
    owner_uid = f"github-conn-{uuid.uuid4().hex[:8]}@example.com"
    yield owner_uid
    get_client().collection(github_connections.COLLECTION).document(owner_uid).delete()


def test_an_unconnected_user_has_no_connection(owner):
    assert has_github_connection(owner) is False
    assert get_decrypted_token(owner) is None


def test_a_saved_token_round_trips_through_firestore(owner):
    save_github_token(owner, "ghp_exampleTokenValue1234567890")

    assert has_github_connection(owner) is True
    assert get_decrypted_token(owner) == "ghp_exampleTokenValue1234567890"


def test_the_stored_document_never_holds_the_raw_token(owner):
    save_github_token(owner, "ghp_exampleTokenValue1234567890")

    doc = get_client().collection(github_connections.COLLECTION).document(owner).get().to_dict()
    assert "ghp_exampleTokenValue1234567890" not in str(doc)


def test_saving_again_replaces_the_previous_token(owner):
    save_github_token(owner, "ghp_first")
    save_github_token(owner, "ghp_second")

    assert get_decrypted_token(owner) == "ghp_second"


def test_deleting_removes_the_connection(owner):
    save_github_token(owner, "ghp_exampleTokenValue1234567890")

    delete_github_connection(owner)

    assert has_github_connection(owner) is False
    assert get_decrypted_token(owner) is None


def test_one_users_token_does_not_leak_to_another(owner):
    other = f"other-{uuid.uuid4().hex[:8]}@example.com"
    try:
        save_github_token(owner, "ghp_exampleTokenValue1234567890")
        assert has_github_connection(other) is False
    finally:
        get_client().collection(github_connections.COLLECTION).document(other).delete()
