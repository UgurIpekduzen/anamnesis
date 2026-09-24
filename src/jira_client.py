import requests

# The result of get_jira_status goes into the model's context and stays in
# the session history, so it is resent on every later model call. Measured
# on 50 issues shaped like a real project's: JSON objects cost ~2560 tokens,
# compact lines for the first 15 ~530 (APPCE-104).
DEFAULT_LIMIT = 15
MAX_SUMMARY_CHARS = 100


def validate_jira_credentials(email: str, token: str, base_url: str) -> None:
    """Verify email/token/base_url actually authenticate against Jira
    before storing them (see APPCE-87) — a bad value should fail here,
    not silently on first use.

    Raises:
        ValueError: Jira rejected the credentials, or the request itself
            failed (e.g. a malformed base_url).
    """
    try:
        response = requests.get(
            f"{base_url.rstrip('/')}/rest/api/3/myself", auth=(email, token), timeout=10
        )
    except requests.RequestException as e:
        raise ValueError(f"Couldn't reach '{base_url}': {e}")
    if response.status_code == 401:
        raise ValueError("Jira rejected these credentials — check the email, token, and workspace URL.")
    response.raise_for_status()


def _format_issue(issue: dict) -> str:
    summary = issue["fields"]["summary"]
    if len(summary) > MAX_SUMMARY_CHARS:
        summary = summary[: MAX_SUMMARY_CHARS - 1] + "…"
    return (
        f'{issue["key"]} · {issue["fields"]["issuetype"]["name"]} · '
        f'{issue["fields"]["status"]["name"]} · {summary}'
    )


def get_jira_status(
    project_key: str, email: str, token: str, base_url: str, limit: int = DEFAULT_LIMIT
) -> dict:
    """Query open issues for a Jira project directly from the Jira REST API.

    Data minimization (APPCE-29): only returns key, issue type, status and
    summary — never assignee/reporter/comment-author fields, since those
    could identify a third party (e.g. a Recruiter.AI candidate referenced
    in a ticket). `summary` itself isn't filtered further: the result is
    never persisted (unlike git_activity_sync's Firestore writes), it's only
    shown back to the same user who already has Jira access, so it doesn't
    create new exposure.

    Kept small on purpose (APPCE-104): the most recently updated `limit`
    issues only, one short line each, with long summaries cut off.

    Args:
        project_key: The Jira project key, e.g. "APPCE".
        email: The connected Jira account's email (see APPCE-87).
        token: The connected Jira account's API token.
        base_url: The connected Jira workspace's URL, e.g.
            "https://example.atlassian.net".
        limit: The most issues to return.

    Returns:
        {"issues": ["KEY · Type · Status · Summary", ...], "truncated": bool}.
        "truncated" is true when the project has more open issues than were
        returned — say so instead of presenting the list as complete.
    """
    jql = f'project = "{project_key}" AND statusCategory != Done ORDER BY updated DESC'
    response = requests.get(
        f"{base_url.rstrip('/')}/rest/api/3/search/jql",
        auth=(email, token),
        # One more than asked for, only to learn whether there is more.
        params={"jql": jql, "fields": "summary,status,issuetype", "maxResults": limit + 1},
        timeout=10,
    )
    response.raise_for_status()
    issues = response.json().get("issues", [])
    return {
        "issues": [_format_issue(issue) for issue in issues[:limit]],
        "truncated": len(issues) > limit,
    }
