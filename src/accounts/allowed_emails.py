import os
import time

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

# A second, independent cache (APPCE-122): which extra emails are exempt
# from the tester lifetime message cap (src.accounts.usage). Kept as a
# subset of the extra emails above, in the same document — most invited
# users stay subject to the cap; this is an opt-in exception the owner
# grants per email (e.g. a collaborator, not a one-off tester).
_unlimited_cache: set[str] | None = None
_unlimited_cache_loaded_at: float = 0.0

_DOC_PATH = ("config", "allowed_emails")


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


def remove_allowed_email(email: str) -> None:
    client = get_client()
    doc_ref = _doc_ref(client)
    # Also drops any unlimited flag, so it can't linger for an email that
    # is later re-added and would otherwise silently skip the lifetime cap.
    doc_ref.set(
        {"emails": firestore.ArrayRemove([email]), "unlimited_emails": firestore.ArrayRemove([email])}, merge=True
    )
    get_extra_allowed_emails(force_refresh=True)
    get_unlimited_emails(force_refresh=True)


def get_unlimited_emails(force_refresh: bool = False) -> set[str]:
    """Extra allowed emails exempt from the tester lifetime message cap."""
    global _unlimited_cache, _unlimited_cache_loaded_at

    is_stale = (time.time() - _unlimited_cache_loaded_at) > _CACHE_TTL_SECONDS
    if _unlimited_cache is None or is_stale or force_refresh:
        doc = _doc_ref(get_client()).get()
        _unlimited_cache = set(doc.to_dict().get("unlimited_emails", [])) if doc.exists else set()
        _unlimited_cache_loaded_at = time.time()

    return _unlimited_cache


def mark_unlimited(email: str) -> None:
    """Exempt an already-invited email from the lifetime message cap.

    Raises:
        ValueError: email is the owner (already exempt) or isn't on the
            allowlist at all — nothing to mark.
    """
    if email in OWNER_EMAILS:
        raise ValueError("The owner is already exempt from the lifetime cap.")
    if email not in get_extra_allowed_emails():
        raise ValueError("That email isn't on the allowlist.")

    client = get_client()
    doc_ref = _doc_ref(client)
    doc_ref.set({"unlimited_emails": firestore.ArrayUnion([email])}, merge=True)
    get_unlimited_emails(force_refresh=True)


def unmark_unlimited(email: str) -> None:
    client = get_client()
    doc_ref = _doc_ref(client)
    doc_ref.set({"unlimited_emails": firestore.ArrayRemove([email])}, merge=True)
    get_unlimited_emails(force_refresh=True)
