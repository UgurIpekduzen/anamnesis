"""Who may sign in beyond the owner(s) named in Terraform, and their role.
Owner-only."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

from api.deps import require_owner
from src.accounts.allowed_emails import (
    OWNER_EMAILS,
    add_allowed_email,
    get_extra_allowed_emails,
    get_invited_ats,
    get_roles,
    remove_allowed_email,
    set_role,
)
from src.accounts.profiles import MAX_NAME_LENGTH, get_names, set_name
from src.accounts.settings import BOUNDS, DEFAULTS, get_settings, save_settings
from src.accounts.usage import GLOBAL_DAILY_MESSAGE_LIMIT, get_global_today_count, get_usage_for
from src.tools.wipe_user import wipe_user


def _extra_users() -> list[dict]:
    emails = get_extra_allowed_emails()
    roles = get_roles(list(emails))
    return [{"email": email, "role": roles[email]} for email in sorted(emails)]


def _known_email(email: str) -> bool:
    """Whether email is someone this app knows about — the owner or an
    invited email — as opposed to an arbitrary string an owner mistyped."""
    return email in OWNER_EMAILS or email in get_extra_allowed_emails()


router = APIRouter()


# Who can sign in at all beyond the Terraform-configured owner(s) — only an
# owner can view/change this (require_owner), since anyone else granting
# access would defeat the allowlist (APPCE-94). A non-owner never even sees
# this section exists: the frontend just doesn't render it without a
# successful GET.
@router.get("/admin/allowed_emails")
def get_allowed_emails(owner_uid: str = Depends(require_owner)) -> dict:
    extra_users = _extra_users()
    all_emails = list(OWNER_EMAILS) + [u["email"] for u in extra_users]
    return {
        "owner_emails": sorted(OWNER_EMAILS),
        "extra_users": extra_users,
        # A display name the owner set for an email (APPCE-126) — never
        # captured from the user's own Google account. Keyed separately
        # rather than folded into owner_emails/extra_users so those two
        # keep their existing shape.
        "names": get_names(all_emails),
    }


class AllowedEmailCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str = Field(strict=True, min_length=1, max_length=320)


@router.post("/admin/allowed_emails")
def add_allowed_email_endpoint(body: AllowedEmailCreate, owner_uid: str = Depends(require_owner)) -> dict:
    try:
        add_allowed_email(body.email)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"extra_users": _extra_users()}


@router.delete("/admin/allowed_emails/{email}")
def remove_allowed_email_endpoint(email: str, owner_uid: str = Depends(require_owner)) -> dict:
    remove_allowed_email(email)
    return {"extra_users": _extra_users()}


class RoleUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: str = Field(strict=True, min_length=1, max_length=20)


# Change an already-invited email's role between "user" (exempt from the
# tester lifetime message cap, APPCE-122/123 — e.g. a trusted collaborator)
# and "tester" (the default). "admin" isn't settable here: it comes only
# from OWNER_EMAILS in Terraform.
@router.put("/admin/allowed_emails/{email}/role")
def set_role_endpoint(email: str, body: RoleUpdate, owner_uid: str = Depends(require_owner)) -> dict:
    try:
        set_role(email, body.role)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"extra_users": _extra_users()}


class UserWipeConfirm(BaseModel):
    model_config = ConfigDict(extra="forbid")

    confirm_email: str = Field(strict=True, min_length=1, max_length=320)


# Permanently delete an invited user's data — not just remove their access
# (APPCE-123). Destructive and irreversible, so a single click isn't enough:
# the caller must repeat the exact email back (confirm_email), the same
# friction src.tools.db_backup's --confirm-project uses for a whole-database
# wipe. The owner can never be targeted — wipe_user itself refuses, this
# just turns that refusal into a 400 instead of a 500.
@router.post("/admin/users/{email}/wipe")
def wipe_user_endpoint(email: str, body: UserWipeConfirm, owner_uid: str = Depends(require_owner)) -> dict:
    if body.confirm_email != email:
        raise HTTPException(status_code=400, detail="Confirmation email doesn't match.")
    try:
        result = wipe_user(email, confirm=True)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {**result, "extra_users": _extra_users()}


# Today's message count and role for every allowed user, plus the shared
# ceiling (APPCE-122) — the same reasoning as get_allowed_emails above
# applies: owner-only, and the list comes from the allowlist itself rather
# than a separate "users" collection.
@router.get("/admin/usage")
def get_usage(owner_uid: str = Depends(require_owner)) -> dict:
    emails = OWNER_EMAILS | get_extra_allowed_emails()
    return {
        "users": get_usage_for(list(emails)),
        "global": {"count": get_global_today_count(), "limit": GLOBAL_DAILY_MESSAGE_LIMIT},
    }


class SettingsUpdate(BaseModel):
    # forbid: an unknown field is a client bug. strict: "5" or true must
    # not be quietly coerced into a valid int. Same shape the user's own
    # PUT /settings used before APPCE-124 moved this here.
    model_config = ConfigDict(extra="forbid")

    history_turns: int = Field(strict=True, ge=BOUNDS["history_turns"][0], le=BOUNDS["history_turns"][1])
    daily_message_warning_threshold: int = Field(
        strict=True,
        ge=BOUNDS["daily_message_warning_threshold"][0],
        le=BOUNDS["daily_message_warning_threshold"][1],
    )


def _settings_response(settings: dict) -> dict:
    # limits/defaults ride along so the admin UI can render min/max and
    # know what "reset" means from the one source of truth.
    return {
        **settings,
        "limits": {name: {"min": low, "max": high} for name, (low, high) in BOUNDS.items()},
        "defaults": dict(DEFAULTS),
    }


# history_turns/daily_message_warning_threshold used to be each user's own
# setting; APPCE-124 moved them here, as one shared value for everyone, not
# per email — history_turns is really a cost lever (it scales the tokens
# resent to the shared agent_sa on every message), the same kind of knob as
# DAILY_MESSAGE_HARD_LIMIT/GLOBAL_DAILY_MESSAGE_LIMIT, not something each
# invited user should tune for themselves.
@router.get("/admin/settings")
def get_shared_settings(owner_uid: str = Depends(require_owner)) -> dict:
    return _settings_response(get_settings())


@router.put("/admin/settings")
def set_shared_settings(body: SettingsUpdate, owner_uid: str = Depends(require_owner)) -> dict:
    return _settings_response(save_settings(body.model_dump()))


# Merges what get_allowed_emails/get_usage/get_names each separately
# expose into rows the Users table can page and search through — the
# owner/extra split and separate usage call made sense before a name (and
# the need to search by it) existed, but the table always showed them as
# one list anyway (APPCE-126). offset/limit are in-memory paging over
# OWNER_EMAILS | get_extra_allowed_emails() (never more than a handful of
# invited testers in practice), not a Firestore-cursor query — there's no
# per-user document to page over, only this array-backed allowlist.
@router.get("/admin/users")
def list_users(
    q: str = Query("", max_length=200),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    owner_uid: str = Depends(require_owner),
) -> dict:
    emails = OWNER_EMAILS | get_extra_allowed_emails()
    roles = get_roles(list(emails))
    names = get_names(list(emails))
    counts = {u["email"]: u["count"] for u in get_usage_for(list(emails))}
    invited_ats = get_invited_ats(list(emails))

    # Oldest first, so a newly-added email lands at the bottom instead of
    # wherever it falls alphabetically. The owner has no invite record (they
    # come from Terraform, not this flow) — datetime.min sorts them first,
    # ahead of every actual invite.
    rows = [
        {
            "email": email,
            "role": roles[email],
            "name": names.get(email),
            "count": counts.get(email, 0),
            "invited_at": invited_ats[email].isoformat() if email in invited_ats else None,
        }
        for email in sorted(emails, key=lambda e: invited_ats.get(e, datetime.min.replace(tzinfo=timezone.utc)))
    ]

    needle = q.strip().lower()
    if needle:
        rows = [r for r in rows if needle in r["email"].lower() or needle in (r["name"] or "").lower()]

    return {
        "users": rows[offset : offset + limit],
        "total": len(rows),
        "limit": limit,
        "offset": offset,
        "global": {"count": get_global_today_count(), "limit": GLOBAL_DAILY_MESSAGE_LIMIT},
    }


class NameUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Not min_length=1: an empty/whitespace string is how the owner clears
    # a name they set by mistake — set_name treats that as "no name", not
    # an error.
    name: str = Field(strict=True, max_length=MAX_NAME_LENGTH)


# A label the owner chooses for an email — never captured from the user's
# own Google account (APPCE-126) — so people are tellable apart once email
# addresses alone aren't enough. Works for the owner's own email too: same
# reasoning as /admin/settings, no lockout risk in a display name.
@router.put("/admin/users/{email}/name")
def set_user_name(email: str, body: NameUpdate, owner_uid: str = Depends(require_owner)) -> dict:
    if not _known_email(email):
        raise HTTPException(status_code=400, detail="That email isn't on the allowlist.")
    try:
        name = set_name(email, body.name)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"email": email, "name": name}
