import os
import re
import time

from google.cloud import firestore

from src.firestore_client import get_client

# Avoids one Firestore read per write; refreshed periodically so a change
# to config/categories is picked up without restarting the process.
_CACHE_TTL_SECONDS = int(os.environ.get("CATEGORY_CACHE_TTL_SECONDS", 300))

# Module-level cache: shared for the lifetime of the process.
_cache: set[str] | None = None
_cache_loaded_at: float = 0.0

# The only source of truth for what a fresh deployment's categories are —
# ensure_categories_seeded() below writes it (APPCE-93).
DEFAULT_CATEGORIES = ["architecture", "decision", "bug", "status", "todo"]


def _load_categories(client: firestore.Client) -> set[str]:
    doc = client.collection("config").document("categories").get()
    if not doc.exists:
        # Fail loudly instead of silently falling back to an empty set,
        # which would reject every category as invalid.
        raise RuntimeError("config/categories document not found in Firestore")
    return set(doc.to_dict().get("allowed", []))


def ensure_categories_seeded() -> None:
    """Write the default category config if it doesn't exist yet.

    Without this, a fresh deployment's config/categories document would not
    exist and every publish_fact call would fail with the RuntimeError above
    (APPCE-93). Nobody has to seed anything by hand.
    Called once at API startup; a no-op once the document exists, so it
    never overwrites categories someone has customized.
    """
    client = get_client()
    doc_ref = client.collection("config").document("categories")
    if not doc_ref.get().exists:
        doc_ref.set({"allowed": DEFAULT_CATEGORIES})


def get_allowed_categories(force_refresh: bool = False) -> set[str]:
    global _cache, _cache_loaded_at

    is_stale = (time.time() - _cache_loaded_at) > _CACHE_TTL_SECONDS
    if _cache is None or is_stale or force_refresh:
        client = get_client()
        _cache = _load_categories(client)
        _cache_loaded_at = time.time()

    return _cache


def validate_category(category: str) -> None:
    allowed = get_allowed_categories()
    if category not in allowed:
        raise ValueError(
            f"Invalid category '{category}'. Allowed: {sorted(allowed)}"
        )


# --- Per-user categories (APPCE-116) ---------------------------------------
#
# A user keeps their own list. Until they change it they follow the suggested
# one below (no document is stored for them, so a better suggestion later
# reaches everyone who never customised). The global config/categories above
# is on its way out: the steps that follow switch every caller to these.

SUGGESTED_CATEGORIES = [*DEFAULT_CATEGORIES, "note"]

# The names go into the model's prompts (the agent's instruction, the GitHub
# extraction schema's enum), so they are short slugs, never free text, and the
# list is bounded so it can't grow the prompt without limit.
MAX_CATEGORIES = 12
_NAME = re.compile(r"^[a-z][a-z0-9_-]{0,29}$")

USER_COLLECTION = "user_categories"
# Read on every fact write, so a short in-process cache spares Firestore a read
# each time; save/reset write through it.
_USER_CACHE_TTL_SECONDS = 30
_user_cache: dict[str, tuple[float, list[str] | None]] = {}


class InvalidCategory(ValueError):
    """A category that isn't allowed here. A ValueError, so existing handlers
    still catch it; a separate type so an endpoint can tell "this category" from
    "this thing doesn't exist"."""


def validate_category_name(category) -> None:
    """Reject anything that isn't shaped like a category name — a slug, not
    free text. Membership in a user's list is validate_category_for's job; this
    is for places that don't know the owner (the Pub/Sub subscriber)."""
    if not isinstance(category, str) or not _NAME.match(category):
        raise InvalidCategory(f"'{category}' isn't a valid category name.")


def check_category_names(categories) -> list[str]:
    """Normalise (trim, lower-case) and validate a user's whole list.

    Raises:
        ValueError: not a list of 1..MAX_CATEGORIES distinct slugs (a letter,
            then letters, digits, "_" or "-", 30 characters at most).
    """
    if not isinstance(categories, list) or not all(isinstance(c, str) for c in categories):
        raise ValueError("Categories must be a list of names.")
    names = [c.strip().lower() for c in categories]
    if not 1 <= len(names) <= MAX_CATEGORIES:
        raise ValueError(f"Keep between 1 and {MAX_CATEGORIES} categories.")
    for name in names:
        if not _NAME.match(name):
            raise ValueError(
                f"'{name}' isn't a valid category name: start with a letter, then use letters, "
                "digits, '_' or '-', up to 30 characters."
            )
    if len(set(names)) != len(names):
        raise ValueError("Each category can only be listed once.")
    return names


def _stored_categories(owner_uid: str) -> list[str] | None:
    """The user's saved list, or None if they never customised it. A stored
    value that no longer passes the rules is treated as absent, not trusted."""
    cached = _user_cache.get(owner_uid)
    if cached and time.monotonic() - cached[0] < _USER_CACHE_TTL_SECONDS:
        return cached[1]
    doc = get_client().collection(USER_COLLECTION).document(owner_uid).get()
    stored = None
    if doc.exists:
        try:
            stored = check_category_names(doc.to_dict().get("allowed"))
        except ValueError:
            stored = None
    _user_cache[owner_uid] = (time.monotonic(), stored)
    return stored


def get_categories(owner_uid: str) -> list[str]:
    """owner_uid's categories, in their order: their own list or the suggested one."""
    return list(_stored_categories(owner_uid) or SUGGESTED_CATEGORIES)


def get_category_settings(owner_uid: str) -> dict:
    stored = _stored_categories(owner_uid)
    return {
        "categories": list(stored or SUGGESTED_CATEGORIES),
        "suggested": list(SUGGESTED_CATEGORIES),
        "customized": stored is not None,
        "max": MAX_CATEGORIES,
    }


def save_categories(owner_uid: str, categories) -> list[str]:
    """Validate and store owner_uid's whole list. Raises ValueError on a bad one."""
    names = check_category_names(categories)
    get_client().collection(USER_COLLECTION).document(owner_uid).set({"allowed": names})
    _user_cache[owner_uid] = (time.monotonic(), names)
    return list(names)


def reset_categories(owner_uid: str) -> list[str]:
    """Back to the suggested list: the stored document is deleted, not
    overwritten with a copy, so the user follows the suggestion again."""
    get_client().collection(USER_COLLECTION).document(owner_uid).delete()
    _user_cache.pop(owner_uid, None)
    return list(SUGGESTED_CATEGORIES)


def validate_category_for(owner_uid: str, category: str) -> None:
    """Reject a category that isn't in owner_uid's list."""
    allowed = get_categories(owner_uid)
    if category not in allowed:
        raise InvalidCategory(f"Invalid category '{category}'. Allowed: {allowed}")
