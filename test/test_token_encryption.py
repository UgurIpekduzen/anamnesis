import pytest
from cryptography.fernet import Fernet

from src import token_encryption


@pytest.fixture(autouse=True)
def fresh_cache(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN_ENCRYPTION_KEY", Fernet.generate_key().decode())
    token_encryption._get_fernet.cache_clear()
    yield
    token_encryption._get_fernet.cache_clear()


def test_a_token_round_trips_through_encrypt_and_decrypt():
    value = "ghp_exampleTokenValue1234567890"
    ciphertext = token_encryption.encrypt_token(value)
    assert ciphertext != value
    assert token_encryption.decrypt_token(ciphertext) == value


def test_encrypting_the_same_value_twice_gives_different_ciphertext():
    # Fernet includes a random IV, so equal plaintexts must not produce
    # equal ciphertexts — otherwise two users with the same secret would be
    # distinguishable from the stored value alone.
    value = "ghp_exampleTokenValue1234567890"
    assert token_encryption.encrypt_token(value) != token_encryption.encrypt_token(value)


def test_a_missing_key_is_an_error(monkeypatch):
    monkeypatch.delenv("GITHUB_TOKEN_ENCRYPTION_KEY")
    with pytest.raises(RuntimeError):
        token_encryption.encrypt_token("ghp_x")


def test_tampered_ciphertext_fails_to_decrypt():
    ciphertext = token_encryption.encrypt_token("ghp_exampleTokenValue1234567890")
    tampered = ciphertext[:-1] + ("A" if ciphertext[-1] != "A" else "B")
    with pytest.raises(Exception):
        token_encryption.decrypt_token(tampered)
