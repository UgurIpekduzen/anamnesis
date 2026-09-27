import os
import time

from src.core.firestore_client import get_client
from src.accounts.usage import DAILY_MESSAGE_WARNING_THRESHOLD

# Per-user preferences (APPCE-58). The env-configured values used to be the
# only ones; they're now the defaults a user starts from.
DEFAULTS = {
    "history_turns": int(os.environ.get("MAX_HISTORY_TURNS", 20)),
    "daily_message_warning_threshold": DAILY_MESSAGE_WARNING_THRESHOLD,
}

# Hard bounds, enforced on write AND on read. history_turns' upper bound is
# what keeps a user from turning the history cap off and running up the
# shared agent_sa's Vertex AI bill (APPCE-57/59); the threshold is only a
# soft UI warning, so its bounds are about sanity, not cost.
BOUNDS = {
    "history_turns": (1, 50),
    "daily_message_warning_threshold": (1, 1000),
}

# Read on every model call (agent/history.py), so a short in-process cache
# spares Firestore a read per call. save_settings writes through it, so the
# instance that handled the save sees the change immediately; another Cloud
# Run instance can lag by up to this long.
CACHE_TTL_SECONDS = 30
_cache: dict[str, tuple[float, dict]] = {}


def _clean(name: str, value) -> int:
    default = DEFAULTS[name]
    if isinstance(value, bool) or not isinstance(value, int):
        return default
    low, high = BOUNDS[name]
    return min(max(value, low), high)


def get_settings(owner_uid: str) -> dict:
    """Return owner_uid's settings, falling back to the defaults for
    anything unset — and clamping anything stored outside today's bounds."""
    cached = _cache.get(owner_uid)
    if cached and time.monotonic() - cached[0] < CACHE_TTL_SECONDS:
        return dict(cached[1])

    doc = get_client().collection("user_settings").document(owner_uid).get()
    stored = doc.to_dict() if doc.exists else {}
    settings = {name: _clean(name, stored.get(name)) for name in DEFAULTS}

    _cache[owner_uid] = (time.monotonic(), settings)
    return dict(settings)


def save_settings(owner_uid: str, settings: dict) -> dict:
    """Validate and store a full settings set for owner_uid.

    Raises:
        ValueError: on an unknown field, a missing field, or a value outside
            BOUNDS — rejected rather than silently clamped, so the caller
            learns its input was wrong.
    """
    unknown = set(settings) - set(DEFAULTS)
    if unknown:
        raise ValueError(f"Unknown setting(s): {sorted(unknown)}")

    validated = {}
    for name in DEFAULTS:
        if name not in settings:
            raise ValueError(f"Missing setting: {name}")
        value = settings[name]
        low, high = BOUNDS[name]
        if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
            raise ValueError(f"{name} must be an integer between {low} and {high}")
        validated[name] = value

    get_client().collection("user_settings").document(owner_uid).set(validated)
    _cache[owner_uid] = (time.monotonic(), dict(validated))
    return dict(validated)


def reset_settings(owner_uid: str) -> dict:
    """Drop owner_uid's stored settings so they fall back to the defaults.

    Deletes the document rather than writing the default values into it:
    a stored copy would freeze today's defaults for this user, while no
    document means they keep following whatever the defaults become.
    """
    get_client().collection("user_settings").document(owner_uid).delete()
    _cache.pop(owner_uid, None)
    return dict(DEFAULTS)
