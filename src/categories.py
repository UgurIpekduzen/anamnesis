import os
import time

from google.cloud import firestore

from src.firestore_client import get_client

# Avoids one Firestore read per write; refreshed periodically so a change
# to config/categories is picked up without restarting the process.
_CACHE_TTL_SECONDS = int(os.environ.get("CATEGORY_CACHE_TTL_SECONDS", 300))

# Module-level cache: shared for the lifetime of the process.
_cache: set[str] | None = None
_cache_loaded_at: float = 0.0


def _load_categories(client: firestore.Client) -> set[str]:
    doc = client.collection("config").document("categories").get()
    if not doc.exists:
        # Fail loudly instead of silently falling back to an empty set,
        # which would reject every category as invalid.
        raise RuntimeError("config/categories document not found in Firestore")
    return set(doc.to_dict().get("allowed", []))


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
