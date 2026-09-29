import requests

# Fine-grained PATs are the only kind accepted: a classic PAT's
# scopes (e.g. "repo") grant access to a user's entire account, so a leaked
# one is far more damaging than a leaked fine-grained token, which is
# limited to the repos its owner explicitly selected. The prefix alone is
# enough to tell them apart — classic tokens start with "ghp_".
FINE_GRAINED_PREFIX = "github_pat_"


def validate_github_token(token: str) -> None:
    """Reject anything that isn't a live, fine-grained GitHub PAT.

    Raises:
        ValueError: the token is the wrong kind, or GitHub doesn't
            recognize it — either way, nothing gets stored.
    """
    if not token.startswith(FINE_GRAINED_PREFIX):
        raise ValueError(
            "Only fine-grained personal access tokens are accepted "
            f"(should start with '{FINE_GRAINED_PREFIX}'). Classic tokens can "
            "grant access to your whole account and are not allowed here."
        )
    response = requests.get(
        "https://api.github.com/user",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
        timeout=10,
    )
    if response.status_code == 401:
        raise ValueError("GitHub rejected this token — check that it's valid and hasn't expired.")
    response.raise_for_status()
