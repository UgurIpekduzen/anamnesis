import os
from functools import lru_cache

from cryptography.fernet import Fernet


@lru_cache(maxsize=1)
def _get_fernet() -> Fernet:
    key = os.environ.get("GITHUB_TOKEN_ENCRYPTION_KEY")
    if not key:
        raise RuntimeError("GITHUB_TOKEN_ENCRYPTION_KEY is not set (see README setup)")
    return Fernet(key.encode())


def encrypt_github_token(token: str) -> str:
    """Encrypt a user's GitHub PAT for storage — never store the raw value."""
    return _get_fernet().encrypt(token.encode()).decode()


def decrypt_github_token(ciphertext: str) -> str:
    """Decrypt a stored GitHub PAT. Call this only right before using the
    token, and don't let the result linger in a variable longer than it has
    to (see APPCE-79's risk-mitigation notes)."""
    return _get_fernet().decrypt(ciphertext.encode()).decode()
