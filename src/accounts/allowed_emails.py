import os
import time
from datetime import datetime, timezone

from google.cloud import firestore

from src.core.firestore_client import get_client

# The owner set (from Terraform's owner_email, APPCE-56) is always allowed
# and can never be removed via the API below — it's what keeps this
# feature from being able to lock everyone out of their own deployment.
# Anyone else is an "extra" email, added/removed at runtime and stored in
# Firestore instead of requiring a redeploy (APPCE-94).
OWNER_EMAILS = {e.strip() for e in os.environ.get("ALLOWED_EMAILS", "").split(",") if e.strip()}

_CACHE_TTL_SECONDS = int(os.environ.get("ALLOWED_EMAILS_CACHE_TTL_SECONDS", 60))
_cache: set[str] | None = None
_cache_loaded_at: float = 0.0

# Every extra email has one of three roles (APPCE-122/123): the owner is
# always "admin" (from OWNER_EMAILS, never stored here); an extra email is
# "tester" unless it's in this set, in which case it's "user" — exempt from
# the tester lifetime message cap (src.accounts.usage) but still subject to
# the daily and global ones.
#
# Deliberately a plain array of emails (set membership), not a Firestore map
# keyed by the raw email: a map key containing "." — which most real
# addresses do (first.last@...) — would be parsed as a nested field path
# ("roles.first.last@...") instead of one key, silently corrupting other
# entries. get_role() below is what actually exposes the role explicitly;
# this set is just how "user" is stored.
_USER_ROLE_CACHE_TTL_SECONDS = _CACHE_TTL_SECONDS
_user_role_cache: set[str] | None = None
_user_role_cache_loaded_at: float = 0.0

ROLES = ("user", "tester")

_DOC_PATH = ("config", "allowed_emails")

# When each extra email was invited (APPCE-126) — the Users table's default
# sort, oldest first, and shown next to each row. One document per email
# (the document ID, not a map key), same reasoning as user_role_emails
# would have if it weren't an array: a "." in the key would be parsed as a
# nested field path instead of one key. Not read/written through the same
# 60s cache as the rest of this module — it's a display value, not
# something an authorization check depends on, so a plain read is simpler
# and correct.
_INVITED_AT_COLLECTION = "user_invited_at"


def _doc_ref(client: firestore.Client):
    collection, doc_id = _DOC_PATH
    return client.collection(collection).document(doc_id)


def get_extra_allowed_emails(force_refresh: bool = False) -> set[str]:
    """Emails granted access at runtime, beyond the Terraform-configured owner(s).

    Unlike src.facts.categories' config doc, a missing document here just means
    no extra emails have been added yet — not a broken deployment — so
    this returns an empty set instead of raising.
    """
    global _cache, _cache_loaded_at

    is_stale = (time.time() - _cache_loaded_at) > _CACHE_TTL_SECONDS
    if _cache is None or is_stale or force_refresh:
        doc = _doc_ref(get_client()).get()
        _cache = set(doc.to_dict().get("emails", [])) if doc.exists else set()
        _cache_loaded_at = time.time()

    return _cache


def add_allowed_email(email: str) -> None:
    email = email.strip()
    if not email:
        raise ValueError("Email can't be empty.")
    if email in OWNER_EMAILS:
        raise ValueError("This email already has permanent owner access.")

    client = get_client()
    doc_ref = _doc_ref(client)
    doc_ref.set({"emails": firestore.ArrayUnion([email])}, merge=True)
    get_extra_allowed_emails(force_refresh=True)
    client.collection(_INVITED_AT_COLLECTION).document(email).set({"invited_at": datetime.now(timezone.utc)})


def remove_allowed_email(email: str) -> None:
    client = get_client()
    doc_ref = _doc_ref(client)
    # Also drops any "user" role, so it can't linger for an email that is
    # later re-added — re-adding always starts as a tester again (and gets
    # today's date, not the original invite date).
    doc_ref.set(
        {"emails": firestore.ArrayRemove([email]), "user_role_emails": firestore.ArrayRemove([email])}, merge=True
    )
    get_extra_allowed_emails(force_refresh=True)
    _get_user_role_emails(force_refresh=True)
    client.collection(_INVITED_AT_COLLECTION).document(email).delete()


def get_invited_ats(emails: list[str]) -> dict[str, datetime]:
    """When each of emails was invited — the Users table's join date column
    and default sort. An email with no record (the owner, or one added
    before this existed) is simply absent from the result."""
    client = get_client()
    result = {}
    for email in emails:
        doc = client.collection(_INVITED_AT_COLLECTION).document(email).get()
        if doc.exists:
            result[email] = doc.to_dict()["invited_at"]
    return result


def _get_user_role_emails(force_refresh: bool = False) -> set[str]:
    global _user_role_cache, _user_role_cache_loaded_at

    is_stale = (time.time() - _user_role_cache_loaded_at) > _USER_ROLE_CACHE_TTL_SECONDS
    if _user_role_cache is None or is_stale or force_refresh:
        doc = _doc_ref(get_client()).get()
        _user_role_cache = set(doc.to_dict().get("user_role_emails", [])) if doc.exists else set()
        _user_role_cache_loaded_at = time.time()

    return _user_role_cache


def get_role(email: str, force_refresh: bool = False) -> str:
    """The role for any email this app knows about: "admin" for an owner,
    otherwise "user" or "tester" for an extra allowed one (the default, for
    an email that has no role set yet, or isn't on the allowlist at all).

    force_refresh: bypass the cache. Cloud Run runs several instances, each
    with its own cache, so the instance that serves an owner's set_role call
    sees the change immediately (it force-refreshes its own cache) but a
    sibling instance can still have the old role for up to
    _CACHE_TTL_SECONDS. That's fine for a display (admin usage/access views),
    but src.accounts.usage's lifetime-cap check is what the role actually
    gates — a demoted/removed "user" must lose the exemption right away, not
    after a caching window, so it always passes True here.
    """
    if email in OWNER_EMAILS:
        return "admin"
    return "user" if email in _get_user_role_emails(force_refresh=force_refresh) else "tester"


def get_roles(emails: list[str]) -> dict[str, str]:
    """get_role for several emails at once — the admin usage/access views."""
    return {email: get_role(email) for email in emails}


def set_role(email: str, role: str) -> None:
    """Set an already-invited email's role to "user" or "tester".

    Raises:
        ValueError: role isn't one of ROLES, email is the owner (always
            "admin", not settable), or email isn't on the allowlist at all.
    """
    if role not in ROLES:
        raise ValueError(f"Role must be one of {ROLES}.")
    if email in OWNER_EMAILS:
        raise ValueError("The owner is always admin — their role can't be changed.")
    if email not in get_extra_allowed_emails():
        raise ValueError("That email isn't on the allowlist.")

    client = get_client()
    doc_ref = _doc_ref(client)
    if role == "user":
        doc_ref.set({"user_role_emails": firestore.ArrayUnion([email])}, merge=True)
    else:
        doc_ref.set({"user_role_emails": firestore.ArrayRemove([email])}, merge=True)
    _get_user_role_emails(force_refresh=True)
