"""Plain-shape checks for the two identifiers a project is linked to.

Both values end up somewhere sensitive (a Jira query, a GitHub API call made
with the user's token), so they are checked against a strict pattern before
anything stores or uses them. They live here, below the integrations, because
the project code and the integrations both need them.
"""

import re

# A Jira project key: an uppercase letter, then uppercase letters, digits or
# underscores. The key is put into a JQL query (project = "KEY"), so anything
# else — a quote above all — could change what the query means.
_PROJECT_KEY_PATTERN = re.compile(r"^[A-Z][A-Z0-9_]{1,49}$")

# owner/name only — GitHub usernames/orgs are alphanumeric-or-hyphen (not
# leading/trailing), repo names add underscore and dot. Rejecting anything
# else keeps this from ever being treated as an arbitrary URL downstream
# (SSRF risk).
_GITHUB_REPO_PATTERN = re.compile(r"^[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,38})/[a-zA-Z0-9_.-]{1,100}$")


def validate_project_key(project_key: str) -> None:
    """Reject anything that isn't a plain Jira project key such as "APPCE".

    Args:
        project_key (str): The candidate Jira project key to check.

    Raises:
        ValueError: the key has characters a Jira project key can't have.
    """
    if not isinstance(project_key, str) or not _PROJECT_KEY_PATTERN.match(project_key):
        raise ValueError(
            "A Jira project key is uppercase letters, digits and underscores, starting with a letter "
            "(for example APPCE)."
        )


def validate_github_repo(github_repo: str) -> None:
    """Reject anything that isn't a plain "owner/name" GitHub repo.

    Args:
        github_repo (str): The candidate GitHub repo to check, as
            "owner/name".

    Raises:
        ValueError: github_repo isn't a plain "owner/name" string.
    """
    if not isinstance(github_repo, str) or not _GITHUB_REPO_PATTERN.match(github_repo):
        raise ValueError(f"'{github_repo}' doesn't look like a GitHub 'owner/name' repo.")
