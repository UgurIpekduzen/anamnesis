"""Stores and retrieves a user's Jira credentials (email, API token, workspace
URL), token encrypted at rest. Kept separate from client.py (which validates
credentials before they get here) so storage and validation can be tested
and reasoned about independently.
"""

from datetime import datetime, timezone

from src.core.firestore_client import get_client
from src.core.token_encryption import decrypt_token, encrypt_token

# Keyed by owner_uid directly (not nested under a tenant) — a Jira account
# belongs to the user, not to any one project (mirrors
# github_connections.py's reasoning).
COLLECTION = "jira_connections"


def save_jira_credentials(owner_uid: str, email: str, token: str, base_url: str) -> None:
    """Store a user's Jira credentials, token encrypted — never the raw
    value. email and base_url aren't secret, but keeping them
    alongside the token means one document holds everything a call to
    Jira needs.
    """
    client = get_client()
    client.collection(COLLECTION).document(owner_uid).set(
        {
            "email": email,
            "encrypted_token": encrypt_token(token),
            "base_url": base_url.rstrip("/"),
            "connected_at": datetime.now(timezone.utc),
        }
    )


def has_jira_connection(owner_uid: str) -> bool:
    """Whether owner_uid has Jira credentials on file, without decrypting."""
    client = get_client()
    return client.collection(COLLECTION).document(owner_uid).get().exists


def get_jira_base_url(owner_uid: str) -> str | None:
    """The workspace address of the user's connected Jira, or None if they
    haven't connected one.

    Not a secret (the user typed it, and it only names their own workspace),
    so it is read without touching the encrypted token. The UI uses it to
    link a project's Jira key.
    """
    doc = get_client().collection(COLLECTION).document(owner_uid).get()
    return doc.to_dict()["base_url"] if doc.exists else None


def get_jira_credentials(owner_uid: str) -> dict | None:
    """The user's Jira credentials, or None if they haven't connected one.

    Returns:
        A dict with "email", "token" (decrypted), and "base_url", or None.
        Call this only right before using the token, and don't let the
        result linger in a variable longer than it has to (same
        risk-mitigation reasoning as the GitHub token applies here).
    """
    doc = get_client().collection(COLLECTION).document(owner_uid).get()
    if not doc.exists:
        return None
    data = doc.to_dict()
    return {
        "email": data["email"],
        "token": decrypt_token(data["encrypted_token"]),
        "base_url": data["base_url"],
    }


def delete_jira_connection(owner_uid: str) -> None:
    """Disconnect Jira — deletes the stored credentials for good."""
    get_client().collection(COLLECTION).document(owner_uid).delete()
