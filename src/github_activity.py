import requests

from src.github_connections import get_decrypted_token
from src.tenants import get_owned_tenant

# Capped for the same reason as MAX_MESSAGE_CHARS (api/main.py, APPCE-59):
# a PR/issue body is free text from a third party, potentially large, and
# whatever this returns eventually reaches an LLM call (APPCE-81) — an
# unbounded body is both a cost risk and a bigger prompt-injection payload.
MAX_BODY_CHARS = 2000

DEFAULT_LIMIT = 10


def _headers(owner_uid: str) -> dict:
    token = get_decrypted_token(owner_uid)
    if not token:
        raise ValueError("No GitHub connection on file for this user.")
    return {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}


def _repo_for(tenant_id: str, owner_uid: str) -> str:
    tenant = get_owned_tenant(tenant_id, owner_uid)
    repo = tenant.get("github_repo")
    if not repo:
        raise ValueError(f"Tenant '{tenant_id}' has no GitHub repo attached.")
    return repo


def _truncate(text: str | None) -> str:
    if not text:
        return ""
    return text if len(text) <= MAX_BODY_CHARS else text[:MAX_BODY_CHARS] + "…"


def fetch_recent_pull_requests(
    owner_uid: str, tenant_id: str, limit: int = DEFAULT_LIMIT, state: str = "all"
) -> list[dict]:
    """Recently updated pull requests for a tenant's linked GitHub repo.

    Data minimization: no comments, no reviewer/assignee identities — those
    could name a third party who never consented to being summarized here
    (see APPCE-29). Only what's needed to describe the PR itself.
    """
    repo = _repo_for(tenant_id, owner_uid)
    response = requests.get(
        f"https://api.github.com/repos/{repo}/pulls",
        params={"state": state, "sort": "updated", "direction": "desc", "per_page": limit},
        headers=_headers(owner_uid),
        timeout=10,
    )
    response.raise_for_status()
    return [
        {
            "number": pr["number"],
            "title": pr["title"],
            "body": _truncate(pr.get("body")),
            "state": pr["state"],
            "updated_at": pr["updated_at"],
            "url": pr["html_url"],
        }
        for pr in response.json()
    ]


def fetch_recent_issues(
    owner_uid: str, tenant_id: str, limit: int = DEFAULT_LIMIT, state: str = "all"
) -> list[dict]:
    """Recently updated issues for a tenant's linked GitHub repo.

    GitHub's /issues endpoint also returns pull requests (they share the
    same underlying object) — those are filtered out so this only returns
    real issues, matching fetch_recent_pull_requests' own scope.
    """
    repo = _repo_for(tenant_id, owner_uid)
    response = requests.get(
        f"https://api.github.com/repos/{repo}/issues",
        params={"state": state, "sort": "updated", "direction": "desc", "per_page": limit},
        headers=_headers(owner_uid),
        timeout=10,
    )
    response.raise_for_status()
    return [
        {
            "number": issue["number"],
            "title": issue["title"],
            "body": _truncate(issue.get("body")),
            "state": issue["state"],
            "updated_at": issue["updated_at"],
            "url": issue["html_url"],
        }
        for issue in response.json()
        if "pull_request" not in issue
    ]


def get_github_status(owner_uid: str, tenant_id: str) -> dict:
    """Currently open pull requests and issues for a tenant's linked repo —
    live data, not stored facts (mirrors src.jira_client.get_jira_status).

    Bodies are dropped entirely (not just truncated): this feeds straight
    into an ongoing chat turn where the agent also holds write tools
    (publish_fact, delete_tenant, ...), unlike the isolated, tool-less
    call in src.github_fact_extraction — so untrusted PR/issue text is
    kept out of that context as much as possible (see APPCE-83 comment).
    Titles alone can't be fully avoided (the point is knowing what's
    open) — the agent's instruction frames them as data, not instructions.
    """
    pull_requests = fetch_recent_pull_requests(owner_uid, tenant_id, state="open")
    issues = fetch_recent_issues(owner_uid, tenant_id, state="open")
    return {
        "pull_requests": [{k: v for k, v in pr.items() if k != "body"} for pr in pull_requests],
        "issues": [{k: v for k, v in issue.items() if k != "body"} for issue in issues],
    }
