"""Who may sign in beyond the owner(s) named in Terraform. Owner-only."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from api.deps import require_owner
from src.accounts.allowed_emails import (
    OWNER_EMAILS,
    add_allowed_email,
    get_extra_allowed_emails,
    get_unlimited_emails,
    mark_unlimited,
    remove_allowed_email,
    unmark_unlimited,
)
from src.accounts.usage import GLOBAL_DAILY_MESSAGE_LIMIT, get_global_today_count, get_usage_for

router = APIRouter()


# Who can sign in at all beyond the Terraform-configured owner(s) — only an
# owner can view/change this (require_owner), since anyone else granting
# access would defeat the allowlist (APPCE-94). A non-owner never even sees
# this section exists: the frontend just doesn't render it without a
# successful GET.
@router.get("/admin/allowed_emails")
def get_allowed_emails(owner_uid: str = Depends(require_owner)) -> dict:
    return {
        "owner_emails": sorted(OWNER_EMAILS),
        "extra_emails": sorted(get_extra_allowed_emails()),
        # Which extra emails are exempt from the tester lifetime cap (APPCE-122).
        "unlimited_emails": sorted(get_unlimited_emails()),
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
    return {"extra_emails": sorted(get_extra_allowed_emails())}


@router.delete("/admin/allowed_emails/{email}")
def remove_allowed_email_endpoint(email: str, owner_uid: str = Depends(require_owner)) -> dict:
    remove_allowed_email(email)
    return {"extra_emails": sorted(get_extra_allowed_emails())}


# Today's message count for every allowed user, plus the shared ceiling
# (APPCE-122) — the same reasoning as get_allowed_emails above applies:
# owner-only, and the list comes from the allowlist itself rather than a
# separate "users" collection.
@router.get("/admin/usage")
def get_usage(owner_uid: str = Depends(require_owner)) -> dict:
    emails = OWNER_EMAILS | get_extra_allowed_emails()
    return {
        "users": get_usage_for(list(emails)),
        "global": {"count": get_global_today_count(), "limit": GLOBAL_DAILY_MESSAGE_LIMIT},
    }


# Exempt one already-invited email from the tester lifetime message cap
# (APPCE-122) — a collaborator you trust, as opposed to a one-off tester.
@router.post("/admin/allowed_emails/{email}/unlimited")
def mark_unlimited_endpoint(email: str, owner_uid: str = Depends(require_owner)) -> dict:
    try:
        mark_unlimited(email)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"unlimited_emails": sorted(get_unlimited_emails())}


@router.delete("/admin/allowed_emails/{email}/unlimited")
def unmark_unlimited_endpoint(email: str, owner_uid: str = Depends(require_owner)) -> dict:
    unmark_unlimited(email)
    return {"unlimited_emails": sorted(get_unlimited_emails())}
