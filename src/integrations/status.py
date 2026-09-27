"""What is open in a project's linked Jira project and GitHub repo, for the
Status panel (APPCE-110): the same live data the chat tools read, with no
model in between — exact, and it costs no tokens.

Each function returns a dict with a "state": "ok" (with the data),
"not_linked" (the project has no key / repo), "not_connected" (the user
hasn't connected the account) or "error" (with a message safe to show).
"""

import requests

from src.integrations.github.activity import get_github_status
from src.integrations.github.connections import has_github_connection
from src.integrations.jira.client import get_jira_status
from src.integrations.jira.connections import get_jira_credentials
from src.projects.tenants import get_owned_tenant


_NOT_FOUND = {"Jira": "Jira couldn't find the project.", "GitHub": "GitHub couldn't find the repo, or the token has no access to it."}


def _failure(service: str, exc: Exception) -> str:
    # Never the exception text: a library's message can echo a URL or a header.
    if isinstance(exc, requests.HTTPError) and exc.response is not None:
        code = exc.response.status_code
        if code == 401:
            return f"{service} rejected the saved credentials. Reconnect it in Settings."
        if code == 403:
            return f"{service} refused the request (permissions or a rate limit)."
        if code == 404:
            return _NOT_FOUND[service]
        return f"{service} answered with HTTP {code}."
    if isinstance(exc, requests.RequestException):
        return f"Couldn't reach {service}."
    return f"Couldn't read {service}."


def _jira_issue(line: str, base_url: str) -> dict:
    # get_jira_status returns "KEY · Type · Status · Summary" lines (APPCE-104).
    key, kind, status, summary = line.split(" · ", 3)
    return {"key": key, "type": kind, "status": status, "summary": summary, "url": f"{base_url}/browse/{key}"}


def get_project_jira_status(tenant_id: str, owner_uid: str) -> dict:
    """Open Jira issues of the project's linked Jira project.

    Raises:
        PermissionError: the project isn't this user's.
    """
    project_key = get_owned_tenant(tenant_id, owner_uid).get("jira_project_key")
    if not project_key:
        return {"state": "not_linked"}
    try:
        credentials = get_jira_credentials(owner_uid)
    except ValueError as exc:
        # A saved token the current key can't read: its message says to reconnect.
        return {"state": "error", "message": str(exc)}
    if credentials is None:
        return {"state": "not_connected"}
    try:
        result = get_jira_status(project_key, **credentials)
    except Exception as exc:
        return {"state": "error", "message": _failure("Jira", exc)}
    base_url = credentials["base_url"].rstrip("/")
    return {
        "state": "ok",
        "project_key": project_key,
        "issues": [_jira_issue(line, base_url) for line in result["issues"]],
        "truncated": result["truncated"],
    }


def get_project_github_status(tenant_id: str, owner_uid: str) -> dict:
    """Open pull requests and issues of the project's linked GitHub repo.

    Raises:
        PermissionError: the project isn't this user's.
    """
    repo = get_owned_tenant(tenant_id, owner_uid).get("github_repo")
    if not repo:
        return {"state": "not_linked"}
    if not has_github_connection(owner_uid):
        return {"state": "not_connected"}
    try:
        result = get_github_status(owner_uid, tenant_id)
    except Exception as exc:
        return {"state": "error", "message": _failure("GitHub", exc)}
    return {
        "state": "ok",
        "repo": repo,
        "pull_requests": [{"number": pr["number"], "title": pr["title"], "url": pr["url"]} for pr in result["pull_requests"]],
        "issues": [{"number": i["number"], "title": i["title"], "url": i["url"]} for i in result["issues"]],
    }
