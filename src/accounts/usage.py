import os
from datetime import datetime, time, timedelta, timezone

from google.cloud import firestore

from src.core.firestore_client import get_client

# A soft, visible warning threshold — not an enforced limit. One shared
# agent_sa serves every user's Vertex AI calls, so a single user running
# up a large daily count is worth surfacing before it becomes a real
# quota/cost problem (see APPCE-49).
DAILY_MESSAGE_WARNING_THRESHOLD = int(os.environ.get("DAILY_MESSAGE_WARNING_THRESHOLD", 100))

# The enforced ceiling (APPCE-102), as opposed to the soft warning above:
# messages past it are refused before any model call is made. It is a cost
# backstop against a runaway or stolen session, not a product quota — normal
# use should never see it. Deliberately an environment variable and not a
# user setting, so nobody can raise their own ceiling. A message can trigger
# up to MAX_LLM_CALLS_PER_TURN model calls, so this bounds messages, not
# tokens.
DAILY_MESSAGE_HARD_LIMIT = int(os.environ.get("DAILY_MESSAGE_HARD_LIMIT", 200))


class DailyLimitExceeded(Exception):
    def __init__(self, limit: int):
        super().__init__(f"Daily message limit of {limit} reached")
        self.limit = limit


@firestore.transactional
def _count_message(transaction, doc_ref, today: str, limit: int) -> int:
    snapshot = doc_ref.get(transaction=transaction)
    data = snapshot.to_dict() if snapshot.exists else {}
    current = data.get("message_count", 0) if data.get("date") == today else 0
    if current >= limit:
        # Nothing is written, so refused messages don't inflate the count.
        raise DailyLimitExceeded(limit)
    transaction.set(doc_ref, {"date": today, "message_count": current + 1})
    return current + 1


def record_message(owner_uid: str) -> int:
    """Count one chat message for owner_uid and return today's running
    count (UTC calendar day).

    Raises DailyLimitExceeded, without counting, once the day's hard limit
    is reached. The read and the write happen in one transaction, so two
    messages sent at the same moment can't both slip under the limit.
    """
    today = datetime.now(timezone.utc).date().isoformat()
    doc_ref = get_client().collection("usage").document(owner_uid)
    return _count_message(get_client().transaction(), doc_ref, today, DAILY_MESSAGE_HARD_LIMIT)


def next_reset_at() -> datetime:
    """When the day's count starts over: the next midnight UTC."""
    tomorrow = datetime.now(timezone.utc).date() + timedelta(days=1)
    return datetime.combine(tomorrow, time.min, tzinfo=timezone.utc)


def get_today_count(owner_uid: str) -> int:
    """Return today's message count for owner_uid without recording one."""
    today = datetime.now(timezone.utc).date().isoformat()
    client = get_client()
    doc = client.collection("usage").document(owner_uid).get()
    if not doc.exists:
        return 0
    data = doc.to_dict()
    return data.get("message_count", 0) if data.get("date") == today else 0
