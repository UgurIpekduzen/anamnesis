import os

import requests
from dotenv import load_dotenv

load_dotenv(os.environ.get("DOTENV_PATH", ".env"))


def _auth() -> tuple[str, str]:
    email = os.environ.get("JIRA_EMAIL")
    token = os.environ.get("JIRA_API_TOKEN")
    if not email or not token:
        raise RuntimeError("JIRA_EMAIL / JIRA_API_TOKEN not set (check your .env file)")
    return (email, token)


def _base_url() -> str:
    base_url = os.environ.get("JIRA_BASE_URL")
    if not base_url:
        raise RuntimeError("JIRA_BASE_URL is not set (check your .env file)")
    return base_url.rstrip("/")


def get_jira_status(project_key: str) -> list[dict]:
    """Query open issues for a Jira project directly from the Jira REST API.

    Data minimization (APPCE-29): only returns key, summary, status, and
    issue type — never assignee/reporter/comment-author fields, since
    those could identify a third party (e.g. a Recruiter.AI candidate
    referenced in a ticket).

    Args:
        project_key: The Jira project key, e.g. "APPCE".

    Returns:
        A list of dicts with "key", "summary", "status", "issue_type".
    """
    jql = f'project = "{project_key}" AND statusCategory != Done ORDER BY updated DESC'
    response = requests.get(
        f"{_base_url()}/rest/api/3/search/jql",
        auth=_auth(),
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
