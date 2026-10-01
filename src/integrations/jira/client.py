"""Validates a Jira Cloud workspace URL and credentials, and queries live
issue status directly from the Jira REST API. Kept separate from
connections.py (which stores credentials) so the network-facing validation
and query logic is testable on its own.
"""

import re
from urllib.parse import urlsplit

import requests

from src.projects.validation import validate_project_key

# The result of get_jira_status goes into the model's context and stays in
# the session history, so it is resent on every later model call. Measured
# on 50 issues shaped like a real project's: JSON objects cost ~2560 tokens,
# compact lines for the first 15 ~530.
DEFAULT_LIMIT = 15
MAX_SUMMARY_CHARS = 100

# The server calls this address with the user's credentials, so it must be a
# Jira Cloud workspace and nothing else: a made-up address could point at the
# server's own network (its metadata service, other services) or at a host that
# collects the token.
_WORKSPACE_HOST = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}\.atlassian\.net$")


def validate_base_url(base_url: str) -> None:
    """Accept only https://<workspace>.atlassian.net.

    Args:
        base_url (str): The candidate Jira workspace URL to check.

    Raises:
        ValueError: anything else — another scheme, host or port, credentials,
            a path, a query.
    """
    problem = ValueError("The workspace URL must look like https://your-workspace.atlassian.net.")
    if not isinstance(base_url, str):
        raise problem
    try:
        parts = urlsplit(base_url.strip())
        port = parts.port
    except ValueError:
        raise problem
    if (
        parts.scheme != "https"
        or not _WORKSPACE_HOST.match((parts.hostname or "").lower())
        or port is not None
        or parts.username is not None
        or parts.password is not None
        or parts.path not in ("", "/")
        or parts.query
        or parts.fragment
    ):
        raise problem


def validate_jira_credentials(email: str, token: str, base_url: str) -> None:
    """Verify email/token/base_url actually authenticate against Jira
    before storing them — a bad value should fail here,
    not silently on first use.

    Args:
        email (str): The Jira account's email to authenticate with.
        token (str): The Jira API token to authenticate with.
        base_url (str): The Jira workspace URL to authenticate against, e.g.
            "https://example.atlassian.net".

    Raises:
        ValueError: the address isn't a Jira Cloud workspace, Jira rejected
            the credentials, or the request itself failed.
    """
    validate_base_url(base_url)
    try:
        # No redirects: an answer from somewhere else is never followed.
        response = requests.get(
            f"{base_url.strip().rstrip('/')}/rest/api/3/myself",
            auth=(email, token),
            timeout=10,
            allow_redirects=False,
        )
    except requests.RequestException as e:
        raise ValueError(f"Couldn't reach '{base_url}': {e}")
    if response.status_code == 401:
        raise ValueError(
            "Jira rejected these credentials — check the email, token, and workspace URL."
        )
    if response.status_code != 200:
        raise ValueError(
            f"Jira answered with HTTP {response.status_code} — check the workspace URL."
        )


def _format_issue(issue: dict, with_resolved_date: bool = False) -> str:
    summary = issue["fields"]["summary"]
    if len(summary) > MAX_SUMMARY_CHARS:
        summary = summary[: MAX_SUMMARY_CHARS - 1] + "…"
    parts = [issue["key"], issue["fields"]["issuetype"]["name"], issue["fields"]["status"]["name"]]
    if with_resolved_date:
        # "2026-09-20T10:04:00.000+0300" -> "2026-09-20"; absent on an issue
        # that was moved to Done without a resolution.
        parts.append((issue["fields"].get("resolutiondate") or "no date")[:10])
    return " · ".join([*parts, summary])


def _search(
    jql: str, fields: str, email: str, token: str, base_url: str, limit: int, resolved: bool
) -> dict:
    # An address saved before it was checked may still be in the database.
    validate_base_url(base_url)
    response = requests.get(
        f"{base_url.rstrip('/')}/rest/api/3/search/jql",
        auth=(email, token),
        allow_redirects=False,
        # One more than asked for, only to learn whether there is more.
        params={"jql": jql, "fields": fields, "maxResults": limit + 1},
        timeout=10,
    )
    response.raise_for_status()
    issues = response.json().get("issues", [])
    return {
        "issues": [_format_issue(issue, resolved) for issue in issues[:limit]],
        "truncated": len(issues) > limit,
    }


def get_jira_status(
    project_key: str, email: str, token: str, base_url: str, limit: int = DEFAULT_LIMIT
) -> dict:
    """Query open issues for a Jira project directly from the Jira REST API.

    Data minimization: only returns key, issue type, status and
    summary — never assignee/reporter/comment-author fields, since those
    could identify a third party (e.g. a job candidate referenced
    in a ticket). `summary` itself isn't filtered further: the result is
    never persisted, it's only shown back to the same user who already has
    Jira access, so it doesn't create new exposure.

    Kept small on purpose: the most recently updated `limit`
    issues only, one short line each, with long summaries cut off.

    Args:
        project_key (str): The Jira project key, e.g. "APPCE".
        email (str): The connected Jira account's email.
        token (str): The connected Jira account's API token.
        base_url (str): The connected Jira workspace's URL, e.g.
            "https://example.atlassian.net".
        limit (int): The most issues to return.

    Returns:
        {"issues": ["KEY · Type · Status · Summary", ...], "truncated": bool}.
        "truncated" is true when the project has more open issues than were
        returned — say so instead of presenting the list as complete.
    """
    # A key saved before it was validated may still be in the database.
    validate_project_key(project_key)
    jql = f'project = "{project_key}" AND statusCategory != Done ORDER BY updated DESC'
    return _search(jql, "summary,status,issuetype", email, token, base_url, limit, resolved=False)


def get_jira_recently_done(
    project_key: str, email: str, token: str, base_url: str, limit: int = DEFAULT_LIMIT
) -> dict:
    """Recently finished issues of a Jira project — what was done lately.

    Same data minimization and size limits as get_jira_status: key, type,
    status, resolution date and a cut-off summary, never people. The most
    recently updated `limit` done issues only.

    Args:
        project_key (str): The Jira project key, e.g. "APPCE".
        email (str): The connected Jira account's email.
        token (str): The connected Jira account's API token.
        base_url (str): The connected Jira workspace's URL, e.g.
            "https://example.atlassian.net".
        limit (int): The most issues to return.

    Returns:
        {"issues": ["KEY · Type · Status · YYYY-MM-DD · Summary", ...],
        "truncated": bool} — "truncated" is true when there are more.
    """
    validate_project_key(project_key)
    jql = f'project = "{project_key}" AND statusCategory = Done ORDER BY updated DESC'
    return _search(
        jql, "summary,status,issuetype,resolutiondate", email, token, base_url, limit, resolved=True
    )
