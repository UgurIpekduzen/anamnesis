"""Owner-set display names for allowed emails, shown in the admin Users
table once email addresses alone aren't enough to tell people apart."""

from src.core.firestore_client import get_client

# A display name for an allowed email, set by the owner from the Admin
# window — never captured from the user's own Google account,
# so it's purely a label the owner chooses to tell people apart in the
# Users table once email addresses alone aren't enough.
#
# One document per email (the document ID, not a map key inside a shared
# doc) — same reasoning as usage/github_connections/jira_connections: a
# Firestore map key containing "." (most real email addresses) would be
# parsed as a nested field path instead of one key, but a document ID has
# no such restriction.
COLLECTION = "user_profiles"
MAX_NAME_LENGTH = 100


def get_name(email: str) -> str | None:
    """The display name the owner set for email, or None if they haven't
    set one (or it's been cleared).

    Args:
        email (str): The email address to look up.
    """
    doc = get_client().collection(COLLECTION).document(email).get()
    return doc.to_dict().get("name") if doc.exists else None


def get_names(emails: list[str]) -> dict[str, str]:
    """get_name for several emails at once — the admin Users table.

    Args:
        emails (list[str]): The email addresses to look up.
    """
    return {email: name for email in emails if (name := get_name(email)) is not None}


def set_name(email: str, name: str) -> str | None:
    """Set (or, with an empty/whitespace-only name, clear) email's display
    name. Returns the stored name, or None if cleared.

    Args:
        email (str): The email address to set the display name for.
        name (str): The display name to store, or an empty/whitespace-only
            string to clear it.

    Raises:
        ValueError: name is longer than MAX_NAME_LENGTH.
    """
    name = name.strip()
    if len(name) > MAX_NAME_LENGTH:
        raise ValueError(f"Name can't be longer than {MAX_NAME_LENGTH} characters.")

    doc_ref = get_client().collection(COLLECTION).document(email)
    if not name:
        doc_ref.delete()
        return None
    doc_ref.set({"name": name})
    return name
