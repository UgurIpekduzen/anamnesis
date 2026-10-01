"""Integration tests for re-encrypting stored tokens when the encryption key rotates."""

import uuid

import pytest
from cryptography.fernet import Fernet

from src.tools import key_rotation

from src.core import token_encryption
from src.core.firestore_client import get_client
from src.integrations.github.connections import get_decrypted_token, save_github_token
from src.integrations.jira.connections import get_jira_credentials, save_jira_credentials


def _use_keys(monkeypatch, *keys):
    monkeypatch.setenv("GITHUB_TOKEN_ENCRYPTION_KEY", ",".join(keys))
    token_encryption._get_fernet.cache_clear()


@pytest.fixture(autouse=True)
def fresh_cache():
    """Clear the cached Fernet instance after each test so key changes in one test don't leak into the next."""
    yield
    token_encryption._get_fernet.cache_clear()


@pytest.fixture
def owner():
    """Yield a unique owner UID and delete its documents from every rotated collection afterwards."""
    owner_uid = f"rotation-{uuid.uuid4().hex[:8]}@example.com"
    yield owner_uid
    client = get_client()
    for collection in key_rotation.COLLECTIONS:
        client.collection(collection).document(owner_uid).delete()


def test_a_rotation_moves_both_kinds_of_token_to_the_new_key(monkeypatch, owner):
    """Rotation re-encrypts both a GitHub token and Jira credentials so they read back with the new key alone."""
    old, new = Fernet.generate_key().decode(), Fernet.generate_key().decode()
    _use_keys(monkeypatch, old)
    save_github_token(owner, "ghp_secret")
    save_jira_credentials(owner, "me@example.com", "jira-secret", "https://example.atlassian.net")

    _use_keys(monkeypatch, new, old)
    result = key_rotation.reencrypt_all_tokens()

    # Other tests' documents may be in the emulator too, so this looks at
    # the two records made here, not at the totals.
    assert result["processed"] >= 2

    # The old key can go: everything reads with the new one alone.
    _use_keys(monkeypatch, new)
    assert get_decrypted_token(owner) == "ghp_secret"
    assert get_jira_credentials(owner)["token"] == "jira-secret"


def test_check_finds_tokens_that_still_need_the_old_key_and_changes_nothing(monkeypatch, owner):
    """A dry-run check reports a token as unreadable when the old key is missing, without rewriting anything."""
    old, new = Fernet.generate_key().decode(), Fernet.generate_key().decode()
    _use_keys(monkeypatch, old)
    save_github_token(owner, "ghp_secret")

    _use_keys(monkeypatch, new)  # the old key is dropped too early
    result = key_rotation.reencrypt_all_tokens(dry_run=True)

    assert result["unreadable"] >= 1
    # Nothing was written: with the old key back, the token still reads.
    _use_keys(monkeypatch, new, old)
    assert get_decrypted_token(owner) == "ghp_secret"


def test_one_unreadable_token_does_not_stop_the_others(monkeypatch, owner):
    """One token that cannot be decrypted with the current keys does not stop rotation of the others."""
    lost, current = Fernet.generate_key().decode(), Fernet.generate_key().decode()
    _use_keys(monkeypatch, lost)
    other_owner = f"rotation-{uuid.uuid4().hex[:8]}@example.com"
    try:
        save_github_token(other_owner, "ghp_written_with_a_lost_key")
        _use_keys(monkeypatch, current)
        save_github_token(owner, "ghp_readable")

        result = key_rotation.reencrypt_all_tokens()

        assert result["unreadable"] >= 1
        assert get_decrypted_token(owner) == "ghp_readable"
    finally:
        get_client().collection("github_connections").document(other_owner).delete()


def test_main_exits_non_zero_when_something_is_unreadable(monkeypatch, owner):
    """The CLI's check command exits with a non-zero status when a stored token is unreadable."""
    lost, current = Fernet.generate_key().decode(), Fernet.generate_key().decode()
    _use_keys(monkeypatch, lost)
    save_github_token(owner, "ghp_x")

    _use_keys(monkeypatch, current)
    assert key_rotation.main(["check"]) == 1
