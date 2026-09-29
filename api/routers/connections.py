"""The signed-in user's own GitHub and Jira credentials: validated before they
are stored, never returned."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from api.deps import get_current_owner_uid
from src.integrations.github.client import validate_github_token
from src.integrations.github.connections import delete_github_connection, has_github_connection, save_github_token
from src.integrations.jira.client import validate_jira_credentials
from src.integrations.jira.connections import (
    delete_jira_connection,
    get_jira_base_url,
    has_jira_connection,
    save_jira_credentials,
)

router = APIRouter()


class GithubConnectionUpdate(BaseModel):
    """Body for PUT /github/connection: the personal access token to save."""

    model_config = ConfigDict(extra="forbid")

    token: str = Field(strict=True, min_length=1, max_length=255)


@router.get("/github/connection")
def read_github_connection(owner_uid: str = Depends(get_current_owner_uid)) -> dict:
    """Whether the signed-in user has a GitHub token saved."""
    return {"connected": has_github_connection(owner_uid)}


@router.put("/github/connection")
def update_github_connection(
    body: GithubConnectionUpdate, owner_uid: str = Depends(get_current_owner_uid)
) -> dict:
    """Validate and save the signed-in user's GitHub token."""
    # Validated before it ever reaches Firestore — an invalid/wrong-kind
    # token must not get encrypted and stored, only to fail on first use.
    try:
        validate_github_token(body.token)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    save_github_token(owner_uid, body.token)
    return {"connected": True}


@router.delete("/github/connection")
def remove_github_connection(owner_uid: str = Depends(get_current_owner_uid)) -> dict:
    """Delete the signed-in user's saved GitHub token."""
    delete_github_connection(owner_uid)
    return {"connected": False}


class JiraConnectionUpdate(BaseModel):
    """Body for PUT /jira/connection: the credentials to save."""

    model_config = ConfigDict(extra="forbid")

    email: str = Field(strict=True, min_length=1, max_length=255)
    token: str = Field(strict=True, min_length=1, max_length=255)
    base_url: str = Field(strict=True, min_length=1, max_length=255)


@router.get("/jira/connection")
def read_jira_connection(owner_uid: str = Depends(get_current_owner_uid)) -> dict:
    """Whether the signed-in user has Jira credentials saved, and their
    workspace address if so."""
    connected = has_jira_connection(owner_uid)
    # The workspace address (not the token) lets the UI link a project's
    # Jira key; there is nothing to link when nothing is connected.
    return {"connected": connected, "base_url": get_jira_base_url(owner_uid) if connected else None}


@router.put("/jira/connection")
def update_jira_connection(body: JiraConnectionUpdate, owner_uid: str = Depends(get_current_owner_uid)) -> dict:
    """Validate and save the signed-in user's Jira credentials."""
    # Validated before it ever reaches Firestore — bad credentials must
    # not get encrypted and stored, only to fail on first use.
    try:
        validate_jira_credentials(body.email, body.token, body.base_url)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    save_jira_credentials(owner_uid, body.email, body.token, body.base_url.strip())
    return {"connected": True}


@router.delete("/jira/connection")
def remove_jira_connection(owner_uid: str = Depends(get_current_owner_uid)) -> dict:
    """Delete the signed-in user's saved Jira credentials."""
    delete_jira_connection(owner_uid)
    return {"connected": False}
