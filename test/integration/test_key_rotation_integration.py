import uuid

import pytest
from cryptography.fernet import Fernet

from src import key_rotation, token_encryption
from src.firestore_client import get_client
from src.github_connections import get_decrypted_token, save_github_token
from src.jira_connections import get_jira_credentials, save_jira_credentials


def _use_keys(monkeypatch, *keys):
    monkeypatch.setenv("GITHUB_TOKEN_ENCRYPTION_KEY", ",".join(keys))
    token_encryption._get_fernet.cache_clear()


@pytest.fixture(autouse=True)
def fresh_cache():
    yield
    token_encryption._get_fernet.cache_clear()


@pytest.fixture
def owner():
    owner_uid = f"rotation-{uuid.uuid4().hex[:8]}@example.com"
    yield owner_uid
    client = get_client()
    for collection in key_rotation.COLLECTIONS:
        client.collection(collection).document(owner_uid).delete()


def test_a_rotation_moves_both_kinds_of_token_to_the_new_key(monkeypatch, owner):
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
    lost, current = Fernet.generate_key().decode(), Fernet.generate_key().decode()
    _use_keys(monkeypatch, lost)
    save_github_token(owner, "ghp_x")

    _use_keys(monkeypatch, current)
    assert key_rotation.main(["check"]) == 1
