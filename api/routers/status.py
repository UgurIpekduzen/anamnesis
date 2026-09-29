"""What is open in a project's linked Jira project and GitHub repo, read live
with the user's own credentials."""

from fastapi import APIRouter, Depends, HTTPException

from api.deps import get_current_owner_uid
from src.integrations.status import get_project_github_status, get_project_jira_status

router = APIRouter()


# The Status panel: what is open in the project's Jira project and
# GitHub repo, read live with the user's own credentials, no model involved.
@router.get("/tenants/{tenant_id}/jira_status")
def get_jira_status_endpoint(tenant_id: str, owner_uid: str = Depends(get_current_owner_uid)) -> dict:
    """Return what's open in the project's linked Jira project, read live
    with the user's own credentials.

    Raises:
        HTTPException: 404 if tenant_id isn't a project this user owns.
    """
    try:
        return get_project_jira_status(tenant_id, owner_uid)
    except PermissionError:
        raise HTTPException(status_code=404, detail="Project not found")


@router.get("/tenants/{tenant_id}/github_status")
def get_github_status_endpoint(tenant_id: str, owner_uid: str = Depends(get_current_owner_uid)) -> dict:
    """Return what's open in the project's linked GitHub repo, read live
    with the user's own credentials.

    Raises:
        HTTPException: 404 if tenant_id isn't a project this user owns.
    """
    try:
        return get_project_github_status(tenant_id, owner_uid)
    except PermissionError:
        raise HTTPException(status_code=404, detail="Project not found")
