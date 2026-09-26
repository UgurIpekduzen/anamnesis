"""The signed-in user's own settings and today's message count."""

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field

from api.deps import get_current_owner_uid
from src.accounts.settings import BOUNDS, DEFAULTS, get_settings, reset_settings, save_settings
from src.accounts.usage import DAILY_MESSAGE_HARD_LIMIT, get_today_count, next_reset_at

router = APIRouter()


class SettingsUpdate(BaseModel):
    # forbid: an unknown field is a client bug (or an attempt to write
    # arbitrary keys into the user's Firestore doc) — reject, don't ignore.
    # strict: "5" or true must not be quietly coerced into a valid int.
    model_config = ConfigDict(extra="forbid")

    history_turns: int = Field(strict=True, ge=BOUNDS["history_turns"][0], le=BOUNDS["history_turns"][1])
    daily_message_warning_threshold: int = Field(
        strict=True,
        ge=BOUNDS["daily_message_warning_threshold"][0],
        le=BOUNDS["daily_message_warning_threshold"][1],
    )


def _settings_response(settings: dict) -> dict:
    # The bounds and defaults ride along so the UI can render min/max and
    # know what "reset" means from the one source of truth instead of
    # hardcoding its own copies.
    return {
        **settings,
        "limits": {name: {"min": low, "max": high} for name, (low, high) in BOUNDS.items()},
        "defaults": dict(DEFAULTS),
    }


@router.get("/settings")
def read_settings(owner_uid: str = Depends(get_current_owner_uid)) -> dict:
    return _settings_response(get_settings(owner_uid))


@router.put("/settings")
def update_settings(body: SettingsUpdate, owner_uid: str = Depends(get_current_owner_uid)) -> dict:
    # owner_uid comes from the verified token, never the body — a user can
    # only ever write their own settings.
    return _settings_response(save_settings(owner_uid, body.model_dump()))


@router.delete("/settings")
def delete_settings(owner_uid: str = Depends(get_current_owner_uid)) -> dict:
    return _settings_response(reset_settings(owner_uid))


@router.get("/usage")
def get_usage(owner_uid: str = Depends(get_current_owner_uid)) -> dict:
    return {
        "count": get_today_count(owner_uid),
        "threshold": get_settings(owner_uid)["daily_message_warning_threshold"],
        "limit": DAILY_MESSAGE_HARD_LIMIT,
        "resets_at": next_reset_at().isoformat(),
    }
