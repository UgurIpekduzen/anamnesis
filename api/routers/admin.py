"""Who may sign in beyond the owner(s) named in Terraform. Owner-only."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from api.deps import require_owner
from src.accounts.allowed_emails import OWNER_EMAILS, add_allowed_email, get_extra_allowed_emails, remove_allowed_email

router = APIRouter()


# Who can sign in at all beyond the Terraform-configured owner(s) — only an
# owner can view/change this (require_owner), since anyone else granting
# access would defeat the allowlist (APPCE-94). A non-owner never even sees
# this section exists: the frontend just doesn't render it without a
# successful GET.
@router.get("/admin/allowed_emails")
def get_allowed_emails(owner_uid: str = Depends(require_owner)) -> dict:
    return {"owner_emails": sorted(OWNER_EMAILS), "extra_emails": sorted(get_extra_allowed_emails())}


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
