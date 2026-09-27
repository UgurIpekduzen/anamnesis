"""Who may sign in beyond the owner(s) named in Terraform, and their role.
Owner-only."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from api.deps import require_owner
from src.accounts.allowed_emails import (
    OWNER_EMAILS,
    add_allowed_email,
    get_extra_allowed_emails,
    get_roles,
    remove_allowed_email,
    set_role,
)
from src.accounts.usage import GLOBAL_DAILY_MESSAGE_LIMIT, get_global_today_count, get_usage_for
from src.tools.wipe_user import wipe_user


def _extra_users() -> list[dict]:
    emails = get_extra_allowed_emails()
    roles = get_roles(list(emails))
    return [{"email": email, "role": roles[email]} for email in sorted(emails)]


router = APIRouter()


# Who can sign in at all beyond the Terraform-configured owner(s) — only an
# owner can view/change this (require_owner), since anyone else granting
# access would defeat the allowlist (APPCE-94). A non-owner never even sees
# this section exists: the frontend just doesn't render it without a
# successful GET.
@router.get("/admin/allowed_emails")
def get_allowed_emails(owner_uid: str = Depends(require_owner)) -> dict:
    return {"owner_emails": sorted(OWNER_EMAILS), "extra_users": _extra_users()}


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
