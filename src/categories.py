import re
import time

from src.firestore_client import get_client

# --- Per-user categories (APPCE-116) ---------------------------------------
#
# A user keeps their own list. Until they change it they follow the suggested
# one below (no document is stored for them, so a better suggestion later
# reaches everyone who never customised).

SUGGESTED_CATEGORIES = ["architecture", "decision", "bug", "status", "todo", "note"]

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
