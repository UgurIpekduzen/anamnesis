"""The signed-in user's own message count today.

history_turns and daily_message_warning_threshold used to be settable here
too, until they were moved to a shared, owner-only setting
(api/routers/admin.py) — cost levers, not a per-user preference. This
router keeps only the read-only usage summary, which any signed-in user
still needs to see their own progress toward the (now shared) threshold
and the hard limit.
"""

from fastapi import APIRouter, Depends

from api.deps import get_current_owner_uid
from src.accounts.settings import get_settings
from src.accounts.usage import DAILY_MESSAGE_HARD_LIMIT, get_today_count, next_reset_at

router = APIRouter()


@router.get("/usage")
def get_usage(owner_uid: str = Depends(get_current_owner_uid)) -> dict:
    """Return the signed-in user's message count for today, alongside the
    shared warning threshold, the hard limit, and when the count resets."""
    return {
        "count": get_today_count(owner_uid),
        "threshold": get_settings()["daily_message_warning_threshold"],
        "limit": DAILY_MESSAGE_HARD_LIMIT,
        "resets_at": next_reset_at().isoformat(),
    }
