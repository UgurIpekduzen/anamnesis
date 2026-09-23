import requests


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


def get_jira_status(project_key: str, email: str, token: str, base_url: str) -> list[dict]:
    """Query open issues for a Jira project directly from the Jira REST API.

    Data minimization (APPCE-29): only returns key, summary, status, and
    issue type — never assignee/reporter/comment-author fields, since
    those could identify a third party (e.g. a Recruiter.AI candidate
    referenced in a ticket). `summary` itself isn't filtered further: the
    result is never persisted (unlike git_activity_sync's Firestore
    writes), it's only shown back to the same user who already has Jira
    access, so it doesn't create new exposure.

    Args:
        project_key: The Jira project key, e.g. "APPCE".
        email: The connected Jira account's email (see APPCE-87).
        token: The connected Jira account's API token.
        base_url: The connected Jira workspace's URL, e.g.
            "https://example.atlassian.net".

    Returns:
        A list of dicts with "key", "summary", "status", "issue_type".
    """
    jql = f'project = "{project_key}" AND statusCategory != Done ORDER BY updated DESC'
    response = requests.get(
        f"{base_url.rstrip('/')}/rest/api/3/search/jql",
        auth=(email, token),
        params={"jql": jql, "fields": "summary,status,issuetype", "maxResults": 50},
        timeout=10,
    )
    response.raise_for_status()
    return [
        {
            "key": issue["key"],
            "summary": issue["fields"]["summary"],
            "status": issue["fields"]["status"]["name"],
            "issue_type": issue["fields"]["issuetype"]["name"],
        }
        for issue in response.json().get("issues", [])
    ]
