import os
from functools import lru_cache

from cryptography.fernet import Fernet

# Named for its original use (APPCE-79) but not GitHub-specific — the same
# key now also encrypts Jira credentials (APPCE-83 follow-up). Renaming the
# env var/secret would mean a second Secret Manager resource and migration
# for no security benefit, since both secret types share the same threat
# model (see the risk discussion on APPCE-79).
_ENCRYPTION_KEY_ENV_VAR = "GITHUB_TOKEN_ENCRYPTION_KEY"


@lru_cache(maxsize=1)
def _get_fernet() -> Fernet:
    key = os.environ.get(_ENCRYPTION_KEY_ENV_VAR)
    if not key:
        raise RuntimeError(f"{_ENCRYPTION_KEY_ENV_VAR} is not set (see README setup)")
    return Fernet(key.encode())


def encrypt_token(value: str) -> str:
    """Encrypt a secret (a GitHub PAT, a Jira API token, ...) for storage —
    never store the raw value."""
    return _get_fernet().encrypt(value.encode()).decode()


def decrypt_token(ciphertext: str) -> str:
    """Decrypt a stored secret. Call this only right before using it, and
    don't let the result linger in a variable longer than it has to (see
    APPCE-79's risk-mitigation notes)."""
    return _get_fernet().decrypt(ciphertext.encode()).decode()
