"""Shared, owner-configurable settings (history length, warning threshold)
that apply to every user of this deployment, as opposed to a per-user
preference — set once by the owner rather than tuned individually."""

import os
import time

from src.core.firestore_client import get_client
from src.accounts.usage import DAILY_MESSAGE_WARNING_THRESHOLD

# One shared configuration for everyone, not a per-user
# preference: history_turns scales the tokens resent to the shared agent_sa
# on every message, so it's a cost lever the owner sets once, the same way
# DAILY_MESSAGE_HARD_LIMIT and GLOBAL_DAILY_MESSAGE_LIMIT are shared knobs
# rather than something each invited user tunes for themselves. The
# env-configured values are the defaults until the owner changes them.
DEFAULTS = {
    "history_turns": int(os.environ.get("MAX_HISTORY_TURNS", 20)),
    "daily_message_warning_threshold": DAILY_MESSAGE_WARNING_THRESHOLD,
}

# Hard bounds, enforced on write AND on read. history_turns' upper bound is
# what keeps this from being turned off and running up the shared
# agent_sa's Vertex AI bill; the threshold is only a soft UI
# warning, so its bounds are about sanity, not cost.
BOUNDS = {
    "history_turns": (1, 50),
    "daily_message_warning_threshold": (1, 1000),
}

# Read on every model call (agent/history.py) and every chat message, so a
# short in-process cache spares Firestore a read each time. save_settings
# writes through it, so the instance that handled the save sees the change
# immediately; another Cloud Run instance can lag by up to this long.
CACHE_TTL_SECONDS = 30
_cache: tuple[float, dict] | None = None

_DOC_PATH = ("config", "message_settings")


def _doc_ref():
    collection, doc_id = _DOC_PATH
    return get_client().collection(collection).document(doc_id)


def _clean(name: str, value) -> int:
    default = DEFAULTS[name]
    if isinstance(value, bool) or not isinstance(value, int):
        return default
    low, high = BOUNDS[name]
    return min(max(value, low), high)


def get_settings() -> dict:
    """The shared settings, falling back to the defaults for anything
    unset — and clamping anything stored outside today's bounds."""
    global _cache

    if _cache and time.monotonic() - _cache[0] < CACHE_TTL_SECONDS:
        return dict(_cache[1])

    doc = _doc_ref().get()
    stored = doc.to_dict() if doc.exists else {}
    settings = {name: _clean(name, stored.get(name)) for name in DEFAULTS}

    _cache = (time.monotonic(), settings)
    return dict(settings)


def save_settings(settings: dict) -> dict:
    """Validate and store the shared settings. Owner-only — see
    api/routers/admin.py.

    Args:
        settings (dict): The full settings mapping to validate and store —
            must contain exactly the keys in DEFAULTS (history_turns,
            daily_message_warning_threshold), each within BOUNDS.

    Raises:
        ValueError: on an unknown field, a missing field, or a value outside
            BOUNDS — rejected rather than silently clamped, so the caller
            learns its input was wrong.
    """
    global _cache

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

    _doc_ref().set(validated)
    _cache = (time.monotonic(), dict(validated))
    return dict(validated)
