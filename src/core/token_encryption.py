import os
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken, MultiFernet

# Named for its original use (APPCE-79) but not GitHub-specific — the same
# key now also encrypts Jira credentials (APPCE-83 follow-up). Renaming the
# env var/secret would mean a second Secret Manager resource and migration
# for no security benefit, since both secret types share the same threat
# model (see the risk discussion on APPCE-79).
_ENCRYPTION_KEY_ENV_VAR = "GITHUB_TOKEN_ENCRYPTION_KEY"


class UnreadableToken(ValueError):
    """A stored secret can't be decrypted by any current key (APPCE-103).

    A ValueError on purpose: the callers that already turn ValueError into
    a message the user can act on (a missing connection, a bad repo name)
    handle this one the same way.
    """


_UNREADABLE_MESSAGE = (
    "The saved token can't be decrypted (the encryption key has changed). "
    "Reconnect it in Settings."
)


@lru_cache(maxsize=1)
def _get_fernet() -> MultiFernet:
    """The env var holds one key, or several separated by commas — newest
    first (APPCE-103). New secrets are encrypted with the first; every key
    is tried when decrypting. That is what makes a rotation gradual: add a
    new key in front, re-encrypt what is stored, then drop the old key.
    Fernet keys are URL-safe base64, so a comma can't appear inside one.
    """
    raw = os.environ.get(_ENCRYPTION_KEY_ENV_VAR)
    keys = [key.strip() for key in raw.split(",") if key.strip()] if raw else []
    if not keys:
        raise RuntimeError(f"{_ENCRYPTION_KEY_ENV_VAR} is not set (see README setup)")
    return MultiFernet([Fernet(key.encode()) for key in keys])


def encrypt_token(value: str) -> str:
    """Encrypt a secret (a GitHub PAT, a Jira API token, ...) for storage —
    never store the raw value."""
    return _get_fernet().encrypt(value.encode()).decode()


def decrypt_token(ciphertext: str) -> str:
    """Decrypt a stored secret. Call this only right before using it, and
    don't let the result linger in a variable longer than it has to (see
    APPCE-79's risk-mitigation notes).

    Raises:
        UnreadableToken: no current key can decrypt it — the key was lost or
            replaced, or the stored value is damaged.
    """
    try:
        return _get_fernet().decrypt(ciphertext.encode()).decode()
    except InvalidToken:
        raise UnreadableToken(_UNREADABLE_MESSAGE) from None


def rotate_token(ciphertext: str) -> str:
    """Re-encrypt a stored secret with the primary (first) key.

    Decrypts with whichever key made it, so it also moves secrets written
    under an older key. Used by the re-encryption step of a key rotation.

    Raises:
        UnreadableToken: no current key can decrypt it.
    """
    try:
        return _get_fernet().rotate(ciphertext.encode()).decode()
    except InvalidToken:
        raise UnreadableToken(_UNREADABLE_MESSAGE) from None
