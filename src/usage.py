import os
from datetime import datetime, timezone

from src.firestore_client import get_client

# A soft, visible warning threshold — not an enforced limit. One shared
# agent_sa serves every user's Vertex AI calls, so a single user running
# up a large daily count is worth surfacing before it becomes a real
# quota/cost problem (see APPCE-49).
DAILY_MESSAGE_WARNING_THRESHOLD = int(os.environ.get("DAILY_MESSAGE_WARNING_THRESHOLD", 100))


def record_message(owner_uid: str) -> int:
    """Record one chat message for owner_uid and return today's running
    count (UTC calendar day).

    This is a read-then-write, not a transaction — acceptable here since
    it only drives a soft UI warning, not an enforced limit, and this
    project doesn't expect concurrent messages from the same owner_uid.
    """
    today = datetime.now(timezone.utc).date().isoformat()
    client = get_client()
    doc_ref = client.collection("usage").document(owner_uid)
    doc = doc_ref.get()
    data = doc.to_dict() if doc.exists else {}

    count = data.get("message_count", 0) + 1 if data.get("date") == today else 1
    doc_ref.set({"date": today, "message_count": count})
    return count


def get_today_count(owner_uid: str) -> int:
    """Return today's message count for owner_uid without recording one."""
    today = datetime.now(timezone.utc).date().isoformat()
    client = get_client()
    doc = client.collection("usage").document(owner_uid).get()
    if not doc.exists:
        return 0
    data = doc.to_dict()
    return data.get("message_count", 0) if data.get("date") == today else 0
