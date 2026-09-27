import os
from datetime import datetime, time, timedelta, timezone

from google.cloud import firestore

from src.accounts.allowed_emails import OWNER_EMAILS
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

# A ceiling across every user combined (APPCE-122): the per-user limit above
# bounds one runaway session, but says nothing about many invited users each
# staying under their own limit on the same day. Default picked to keep the
# worst case (every day maxed out, all month) around $5 at ~$0.005/message:
# 30 * 0.005 * 30 days = $4.50, with a little headroom under $5.
GLOBAL_DAILY_MESSAGE_LIMIT = int(os.environ.get("GLOBAL_DAILY_MESSAGE_LIMIT", 30))

# Not a valid email (no "@"), so it can never collide with a real owner_uid —
# the one document in this collection that isn't a user's own count.
GLOBAL_USAGE_DOC_ID = "_global"

# A total, never-reset ceiling for invited (non-owner) testers, on top of the
# daily limits above — deliberately separate from them (a day-scoped limit
# alone would let a tester who returns every day use an unbounded amount
# over time). The owner is exempt: they need to be able to use their own
# deployment without limit.
TESTER_LIFETIME_MESSAGE_LIMIT = int(os.environ.get("TESTER_LIFETIME_MESSAGE_LIMIT", 30))


class DailyLimitExceeded(Exception):
    def __init__(self, limit: int, scope: str):
        # scope: "user" (this caller's own limit) or "global" (everyone's,
        # combined) — callers show a different message for each.
        super().__init__(f"Daily message limit of {limit} reached ({scope})")
        self.limit = limit
        self.scope = scope


def _count(snapshot, today: str) -> int:
    data = snapshot.to_dict() if snapshot.exists else {}
    return data.get("message_count", 0) if data.get("date") == today else 0


@firestore.transactional
def _count_message(
    transaction, user_ref, global_ref, today: str, user_limit: int, global_limit: int, lifetime_limit: int | None
) -> int:
    # Both reads happen before either write, as a single transaction requires.
    user_snapshot = user_ref.get(transaction=transaction)
    global_current = _count(global_ref.get(transaction=transaction), today)
    user_current = _count(user_snapshot, today)
    user_data = user_snapshot.to_dict() if user_snapshot.exists else {}
    lifetime_current = user_data.get("lifetime_count", 0)
    # The user's own limit is checked first: it's what the message shown to
    # them should usually reflect, and it's reached far more often in
    # practice than the shared or lifetime ones.
    if user_current >= user_limit:
        raise DailyLimitExceeded(user_limit, "user")
    if lifetime_limit is not None and lifetime_current >= lifetime_limit:
        raise DailyLimitExceeded(lifetime_limit, "lifetime")
    if global_current >= global_limit:
        raise DailyLimitExceeded(global_limit, "global")
    # Nothing is written on any branch above, so a refused attempt inflates
    # no counter.
    transaction.set(
        user_ref, {"date": today, "message_count": user_current + 1, "lifetime_count": lifetime_current + 1}
    )
    transaction.set(global_ref, {"date": today, "message_count": global_current + 1})
    return user_current + 1


def record_message(owner_uid: str) -> int:
    """Count one chat message for owner_uid and return today's running
    count (UTC calendar day). Also counts toward the global ceiling and,
    for a non-owner, the lifetime one.

    Raises DailyLimitExceeded, without counting toward any of them, once
    the user's own hard limit, the lifetime one (testers only), or the
    global one is reached. The reads and the writes happen in one
    transaction, so two messages sent at the same moment can't both slip
    under any limit.
    """
    today = datetime.now(timezone.utc).date().isoformat()
    client = get_client()
    user_ref = client.collection("usage").document(owner_uid)
    global_ref = client.collection("usage").document(GLOBAL_USAGE_DOC_ID)
    lifetime_limit = None if owner_uid in OWNER_EMAILS else TESTER_LIFETIME_MESSAGE_LIMIT
    return _count_message(
        client.transaction(),
        user_ref,
        global_ref,
        today,
        DAILY_MESSAGE_HARD_LIMIT,
        GLOBAL_DAILY_MESSAGE_LIMIT,
        lifetime_limit,
    )


def next_reset_at() -> datetime:
    """When the day's count starts over: the next midnight UTC."""
    tomorrow = datetime.now(timezone.utc).date() + timedelta(days=1)
    return datetime.combine(tomorrow, time.min, tzinfo=timezone.utc)


def get_today_count(owner_uid: str) -> int:
    """Return today's message count for owner_uid without recording one."""
    today = datetime.now(timezone.utc).date().isoformat()
    doc = get_client().collection("usage").document(owner_uid).get()
    return _count(doc, today)


def get_global_today_count() -> int:
    """Return today's message count across every user, without recording one."""
    today = datetime.now(timezone.utc).date().isoformat()
    doc = get_client().collection("usage").document(GLOBAL_USAGE_DOC_ID).get()
    return _count(doc, today)


def get_usage_for(emails: list[str]) -> list[dict]:
    """Today's count for each of the given emails, sorted by email — the
    admin usage table's rows (APPCE-122)."""
    return [{"email": email, "count": get_today_count(email)} for email in sorted(emails)]
