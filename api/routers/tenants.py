"""Projects (tenants): create, rename, delete, and link one to a GitHub repo
and a Jira project. Project management lives here, in the UI's REST calls, and
not in the chat agent."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from api.deps import get_current_owner_uid
from src.projects.tenants import (
    TenantNameTaken,
    add_tenant,
    clear_github_repo,
    clear_jira_project_key,
    delete_tenant,
    list_tenants,
    rename_tenant,
    set_github_repo,
    set_jira_project_key,
)

router = APIRouter()


@router.get("/tenants")
def get_tenants(owner_uid: str = Depends(get_current_owner_uid)) -> list[dict]:
    """Every project owned by the signed-in user."""
    return list_tenants(owner_uid)


class TenantCreate(BaseModel):
    """Body for POST /tenants: the new project's name."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(strict=True, min_length=1, max_length=200)


@router.post("/tenants")
def create_tenant(body: TenantCreate, owner_uid: str = Depends(get_current_owner_uid)) -> dict:
    """Create a new, empty project owned by the signed-in user."""
    # Project lifecycle (create/rename/delete) is deliberately UI-only, not
    # a chat tool — see agent/agent.py's build_agent docstring for why.
    try:
        tenant_id = add_tenant(body.name, owner_uid)
    except TenantNameTaken as exc:
        # The same answer whoever owns the existing project.
        raise HTTPException(status_code=409, detail=f"{exc} Try another name.")
    return {"tenant_id": tenant_id}


class TenantRename(BaseModel):
    """Body for PATCH /tenants/{tenant_id}: the project's new name."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(strict=True, min_length=1, max_length=200)


@router.patch("/tenants/{tenant_id}")
def update_tenant(
    tenant_id: str, body: TenantRename, owner_uid: str = Depends(get_current_owner_uid)
) -> dict:
    """Rename a project owned by the signed-in user.

    Args:
        tenant_id: The project identifier, e.g. "my_project".
    """
    try:
        rename_tenant(tenant_id, body.name, owner_uid)
    except PermissionError:
        raise HTTPException(status_code=404, detail="Project not found")
    return {"status": "renamed"}


@router.delete("/tenants/{tenant_id}")
def remove_tenant(tenant_id: str, owner_uid: str = Depends(get_current_owner_uid)) -> dict:
    """Delete a project owned by the signed-in user, and everything in it.

    Args:
        tenant_id: The project identifier, e.g. "my_project".
    """
    try:
        delete_tenant(tenant_id, owner_uid)
    except PermissionError:
        raise HTTPException(status_code=404, detail="Project not found")
    return {"status": "deleted"}


# Which GitHub repo and Jira project a project is linked to is set here, in
# the UI, and not by the chat agent: these values decide whose repo gets polled
# with the user's token and what goes into a Jira query, and the agent reads
# text other people wrote.
class GithubRepoUpdate(BaseModel):
    """Body for PUT /tenants/{tenant_id}/github_repo: the "owner/name" repo
    to link."""

    model_config = ConfigDict(extra="forbid")

    github_repo: str = Field(strict=True, min_length=1, max_length=140)


class JiraProjectKeyUpdate(BaseModel):
    """Body for PUT /tenants/{tenant_id}/jira_project_key: the Jira project
    key to link."""

    model_config = ConfigDict(extra="forbid")

    jira_project_key: str = Field(strict=True, min_length=1, max_length=60)


@router.put("/tenants/{tenant_id}/github_repo")
def update_github_repo(
    tenant_id: str, body: GithubRepoUpdate, owner_uid: str = Depends(get_current_owner_uid)
) -> dict:
    """Link a project to a GitHub repo, so it gets polled for facts.

    Args:
        tenant_id: The project identifier, e.g. "my_project".
    """
    try:
        set_github_repo(tenant_id, body.github_repo, owner_uid)
    except PermissionError:
        raise HTTPException(status_code=404, detail="Project not found")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"github_repo": body.github_repo}


@router.delete("/tenants/{tenant_id}/github_repo")
def remove_github_repo(tenant_id: str, owner_uid: str = Depends(get_current_owner_uid)) -> dict:
    """Unlink a project's GitHub repo, stopping it being polled.

    Args:
        tenant_id: The project identifier, e.g. "my_project".
    """
    try:
        clear_github_repo(tenant_id, owner_uid)
    except PermissionError:
        raise HTTPException(status_code=404, detail="Project not found")
    return {"github_repo": None}


@router.put("/tenants/{tenant_id}/jira_project_key")
def update_jira_project_key(
    tenant_id: str, body: JiraProjectKeyUpdate, owner_uid: str = Depends(get_current_owner_uid)
) -> dict:
    """Link a project to a Jira project key.

    Args:
        tenant_id: The project identifier, e.g. "my_project".
    """
    try:
        set_jira_project_key(tenant_id, body.jira_project_key, owner_uid)
    except PermissionError:
        raise HTTPException(status_code=404, detail="Project not found")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"jira_project_key": body.jira_project_key}


@router.delete("/tenants/{tenant_id}/jira_project_key")
def remove_jira_project_key(tenant_id: str, owner_uid: str = Depends(get_current_owner_uid)) -> dict:
    """Unlink a project's Jira project key.

    Args:
        tenant_id: The project identifier, e.g. "my_project".
    """
    try:
        clear_jira_project_key(tenant_id, owner_uid)
    except PermissionError:
        raise HTTPException(status_code=404, detail="Project not found")
    return {"jira_project_key": None}
