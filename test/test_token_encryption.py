import pytest
from cryptography.fernet import Fernet

from src import token_encryption
from src.token_encryption import UnreadableToken


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


def _use_keys(monkeypatch, *keys):
    monkeypatch.setenv("GITHUB_TOKEN_ENCRYPTION_KEY", ",".join(keys))
    token_encryption._get_fernet.cache_clear()


def test_a_secret_written_under_an_old_key_is_still_readable_after_a_new_key_is_added(monkeypatch):
    old, new = Fernet.generate_key().decode(), Fernet.generate_key().decode()
    _use_keys(monkeypatch, old)
    ciphertext = token_encryption.encrypt_token("ghp_written_before_the_rotation")

    _use_keys(monkeypatch, new, old)

    assert token_encryption.decrypt_token(ciphertext) == "ghp_written_before_the_rotation"


def test_new_secrets_are_encrypted_with_the_first_key(monkeypatch):
    old, new = Fernet.generate_key().decode(), Fernet.generate_key().decode()
    _use_keys(monkeypatch, new, old)
    ciphertext = token_encryption.encrypt_token("ghp_x")

    # Readable with the new key alone: the old one wasn't used.
    _use_keys(monkeypatch, new)
    assert token_encryption.decrypt_token(ciphertext) == "ghp_x"


def test_rotating_moves_a_secret_to_the_first_key(monkeypatch):
    old, new = Fernet.generate_key().decode(), Fernet.generate_key().decode()
    _use_keys(monkeypatch, old)
    ciphertext = token_encryption.encrypt_token("ghp_x")

    _use_keys(monkeypatch, new, old)
    rotated = token_encryption.rotate_token(ciphertext)

    # Once the old key is dropped, only the rotated copy still reads.
    _use_keys(monkeypatch, new)
    assert token_encryption.decrypt_token(rotated) == "ghp_x"
    with pytest.raises(UnreadableToken):
        token_encryption.decrypt_token(ciphertext)


def test_keys_may_be_separated_by_commas_with_spaces(monkeypatch):
    first, second = Fernet.generate_key().decode(), Fernet.generate_key().decode()
    _use_keys(monkeypatch, first)
    ciphertext = token_encryption.encrypt_token("ghp_x")

    monkeypatch.setenv("GITHUB_TOKEN_ENCRYPTION_KEY", f" {second} , {first} ")
    token_encryption._get_fernet.cache_clear()

    assert token_encryption.decrypt_token(ciphertext) == "ghp_x"


def test_a_lost_key_is_reported_as_an_unreadable_token_with_a_useful_message(monkeypatch):
    _use_keys(monkeypatch, Fernet.generate_key().decode())
    ciphertext = token_encryption.encrypt_token("ghp_x")

    _use_keys(monkeypatch, Fernet.generate_key().decode())
    with pytest.raises(UnreadableToken) as excinfo:
        token_encryption.decrypt_token(ciphertext)

    assert "Reconnect it in Settings" in str(excinfo.value)
    # The value being decrypted must not end up in the message.
    assert ciphertext not in str(excinfo.value)


def test_an_unreadable_token_is_a_value_error():
    # The existing callers that turn ValueError into a user-facing message
    # rely on this.
    assert issubclass(UnreadableToken, ValueError)
