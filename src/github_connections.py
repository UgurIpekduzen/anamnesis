from datetime import datetime, timezone

from src.firestore_client import get_client
from src.github_secrets import decrypt_github_token, encrypt_github_token

# Keyed by owner_uid directly (not nested under a tenant) — a GitHub PAT
# belongs to the user's account, not to any one project (see APPCE-79).
COLLECTION = "github_connections"


def save_github_token(owner_uid: str, token: str) -> None:
    """Store a user's GitHub PAT, encrypted — never the raw value (APPCE-79)."""
    client = get_client()
    client.collection(COLLECTION).document(owner_uid).set(
        {
            "encrypted_token": encrypt_github_token(token),
            "connected_at": datetime.now(timezone.utc),
        }
    )


def has_github_connection(owner_uid: str) -> bool:
    """Whether owner_uid has a GitHub token on file, without decrypting it."""
    client = get_client()
    return client.collection(COLLECTION).document(owner_uid).get().exists


def get_decrypted_token(owner_uid: str) -> str | None:
    """The user's raw GitHub PAT, or None if they haven't connected one.

    Call this only right before using the token (e.g. one GitHub API
    request), and don't let the result linger in a variable longer than it
    has to — see APPCE-79's risk-mitigation notes.
    """
    doc = get_client().collection(COLLECTION).document(owner_uid).get()
    if not doc.exists:
        return None
    return decrypt_github_token(doc.to_dict()["encrypted_token"])


def delete_github_connection(owner_uid: str) -> None:
    """Disconnect GitHub — deletes the stored token for good."""
    get_client().collection(COLLECTION).document(owner_uid).delete()
