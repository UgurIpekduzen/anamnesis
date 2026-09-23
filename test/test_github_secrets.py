import pytest
from cryptography.fernet import Fernet

from src import github_secrets


@pytest.fixture(autouse=True)
def fresh_cache(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN_ENCRYPTION_KEY", Fernet.generate_key().decode())
    github_secrets._get_fernet.cache_clear()
    yield
    github_secrets._get_fernet.cache_clear()


def test_a_token_round_trips_through_encrypt_and_decrypt():
    token = "ghp_exampleTokenValue1234567890"
    ciphertext = github_secrets.encrypt_github_token(token)
    assert ciphertext != token
    assert github_secrets.decrypt_github_token(ciphertext) == token


def test_encrypting_the_same_token_twice_gives_different_ciphertext():
    # Fernet includes a random IV, so equal plaintexts must not produce
    # equal ciphertexts — otherwise two users with the same token would be
    # distinguishable from the stored value alone.
    token = "ghp_exampleTokenValue1234567890"
    assert github_secrets.encrypt_github_token(token) != github_secrets.encrypt_github_token(token)


def test_a_missing_key_is_an_error(monkeypatch):
    monkeypatch.delenv("GITHUB_TOKEN_ENCRYPTION_KEY")
    with pytest.raises(RuntimeError):
        github_secrets.encrypt_github_token("ghp_x")


def test_tampered_ciphertext_fails_to_decrypt():
    ciphertext = github_secrets.encrypt_github_token("ghp_exampleTokenValue1234567890")
    tampered = ciphertext[:-1] + ("A" if ciphertext[-1] != "A" else "B")
    with pytest.raises(Exception):
        github_secrets.decrypt_github_token(tampered)
