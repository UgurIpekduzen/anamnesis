"""Tests for the Jira REST client: status queries, recently-done queries, and credential validation."""

import pytest
import requests

from src.integrations.jira.client import (
    DEFAULT_LIMIT,
    MAX_SUMMARY_CHARS,
    get_jira_recently_done,
    get_jira_status,
    validate_jira_credentials,
)


class FakeResponse:
    """A stand-in for a `requests.Response` with a configurable status and JSON body."""

    def __init__(self, payload=None, status=200):
        """Store the JSON payload and status code to return."""
        self._payload = payload or {}
        self.status_code = status

    def raise_for_status(self):
        """Raise an HTTPError when the configured status code is an error."""
        if self.status_code >= 400:
            raise requests.HTTPError(f"status {self.status_code}")

    def json(self):
        """Return the configured JSON payload."""
        return self._payload


def test_get_jira_status_maps_the_expected_fields(monkeypatch):
    """get_jira_status builds the expected JQL and auth, and maps each issue into a single summary line."""

    def fake_get(url, auth, params, timeout, allow_redirects):
        """Assert the request URL, auth, and JQL, then return one fake issue."""
        assert url == "https://example.atlassian.net/rest/api/3/search/jql"
        assert auth == ("user@example.com", "secret-token")
        assert 'project = "APPCE"' in params["jql"]
        return FakeResponse(
            {
                "issues": [
                    {
                        "key": "APPCE-1",
                        "fields": {
                            "summary": "Fix bug",
                            "status": {"name": "In Progress"},
                            "issuetype": {"name": "Bug"},
                        },
                    }
                ]
            }
        )

    monkeypatch.setattr("src.integrations.jira.client.requests.get", fake_get)

    result = get_jira_status(
        "APPCE", "user@example.com", "secret-token", "https://example.atlassian.net"
    )

    assert result == {"issues": ["APPCE-1 · Bug · In Progress · Fix bug"], "truncated": False}


def _issue(number, summary="Fix bug"):
    return {
        "key": f"APPCE-{number}",
        "fields": {"summary": summary, "status": {"name": "To Do"}, "issuetype": {"name": "Task"}},
    }


def _serving(monkeypatch, issues):
    seen = {}

    def fake_get(url, auth, params, timeout, allow_redirects):
        """Record the request params and return up to maxResults issues, like the real Jira API."""
        seen["params"] = params
        # Like Jira: never more than was asked for.
        return FakeResponse({"issues": issues[: params["maxResults"]]})

    monkeypatch.setattr("src.integrations.jira.client.requests.get", fake_get)
    return seen


def test_only_the_most_recent_issues_up_to_the_limit_are_returned(monkeypatch):
    """When more issues exist than DEFAULT_LIMIT, only the first DEFAULT_LIMIT are returned and the result is marked truncated."""
    _serving(monkeypatch, [_issue(n) for n in range(1, 41)])

    result = get_jira_status("APPCE", "u@example.com", "t", "https://example.atlassian.net")

    assert len(result["issues"]) == DEFAULT_LIMIT
    assert result["issues"][0].startswith("APPCE-1 ")
    assert result["truncated"] is True


def test_it_asks_jira_for_one_more_than_the_limit_only_to_detect_more(monkeypatch):
    """get_jira_status requests limit + 1 issues from Jira, so it can tell whether the result was truncated."""
    seen = _serving(monkeypatch, [_issue(n) for n in range(1, 41)])

    get_jira_status("APPCE", "u@example.com", "t", "https://example.atlassian.net", limit=5)

    assert seen["params"]["maxResults"] == 6


def test_exactly_the_limit_is_not_reported_as_truncated(monkeypatch):
    """When the issue count exactly equals DEFAULT_LIMIT, the result is not marked truncated."""
    _serving(monkeypatch, [_issue(n) for n in range(1, DEFAULT_LIMIT + 1)])

    result = get_jira_status("APPCE", "u@example.com", "t", "https://example.atlassian.net")

    assert len(result["issues"]) == DEFAULT_LIMIT
    assert result["truncated"] is False


def test_a_project_with_no_open_issues_returns_an_empty_list(monkeypatch):
    """A project with no matching issues returns an empty, untruncated issue list."""
    _serving(monkeypatch, [])

    assert get_jira_status("APPCE", "u@example.com", "t", "https://example.atlassian.net") == {
        "issues": [],
        "truncated": False,
    }


def test_a_long_summary_is_cut_off_with_an_ellipsis(monkeypatch):
    """A summary longer than MAX_SUMMARY_CHARS is truncated to that length and ends with an ellipsis."""
    _serving(monkeypatch, [_issue(1, summary="x" * 500)])

    line = get_jira_status("APPCE", "u@example.com", "t", "https://example.atlassian.net")[
        "issues"
    ][0]

    summary = line.split(" · ", 3)[3]
    assert len(summary) == MAX_SUMMARY_CHARS
    assert summary.endswith("…")


def test_a_summary_at_the_limit_is_left_alone(monkeypatch):
    """A summary exactly at MAX_SUMMARY_CHARS is left untouched, with no ellipsis added."""
    _serving(monkeypatch, [_issue(1, summary="y" * MAX_SUMMARY_CHARS)])

    line = get_jira_status("APPCE", "u@example.com", "t", "https://example.atlassian.net")[
        "issues"
    ][0]

    assert line.endswith("y" * MAX_SUMMARY_CHARS)
    assert "…" not in line


def test_get_jira_status_strips_a_trailing_slash_from_the_base_url(monkeypatch):
    """A trailing slash on the configured base URL is stripped before building the request URL."""

    def fake_get(url, auth, params, timeout, allow_redirects):
        """Assert the URL has no double slash from a trailing slash on the base URL."""
        assert url == "https://example.atlassian.net/rest/api/3/search/jql"
        return FakeResponse({"issues": []})

    monkeypatch.setattr("src.integrations.jira.client.requests.get", fake_get)

    get_jira_status("APPCE", "user@example.com", "secret-token", "https://example.atlassian.net/")


def test_validate_jira_credentials_accepts_a_successful_response(monkeypatch):
    """A successful response from Jira does not raise."""
    monkeypatch.setattr(
        "src.integrations.jira.client.requests.get",
        lambda url, auth, timeout, allow_redirects: FakeResponse(),
    )

    validate_jira_credentials("user@example.com", "secret-token", "https://example.atlassian.net")


def test_validate_jira_credentials_rejects_a_401(monkeypatch):
    """A 401 response from Jira is turned into a ValueError."""
    monkeypatch.setattr(
        "src.integrations.jira.client.requests.get",
        lambda url, auth, timeout, allow_redirects: FakeResponse(status=401),
    )

    with pytest.raises(ValueError):
        validate_jira_credentials(
            "user@example.com", "wrong-token", "https://example.atlassian.net"
        )


def test_validate_jira_credentials_wraps_a_connection_failure(monkeypatch):
    """A connection failure while reaching Jira is wrapped in a ValueError."""

    def fake_get(url, auth, timeout, allow_redirects):
        """Simulate a DNS/connection failure."""
        raise requests.ConnectionError("no such host")

    monkeypatch.setattr("src.integrations.jira.client.requests.get", fake_get)

    with pytest.raises(ValueError):
        validate_jira_credentials(
            "user@example.com", "secret-token", "https://not-a-real-host.invalid"
        )


def test_a_bad_key_saved_earlier_never_reaches_jira(monkeypatch):
    """An invalid project key is rejected before any request is made to Jira."""

    def unexpected(*args, **kwargs):
        """Fail the test if a request is made at all."""
        raise AssertionError("no request may be made with an invalid key")

    monkeypatch.setattr("src.integrations.jira.client.requests.get", unexpected)

    with pytest.raises(ValueError):
        get_jira_status('X" OR project != "', "u@example.com", "t", "https://example.atlassian.net")


def test_get_jira_recently_done_asks_for_done_issues_and_shows_the_resolution_date(monkeypatch):
    """get_jira_recently_done queries for done issues and formats each with its resolution date, or "no date" when absent."""
    seen = {}

    def fake_get(url, auth, params, timeout, allow_redirects):
        """Record the request params and return two fake done issues."""
        seen.update(params)
        return FakeResponse(
            {
                "issues": [
                    {
                        "key": "APPCE-7",
                        "fields": {
                            "summary": "Ship it",
                            "status": {"name": "Done"},
                            "issuetype": {"name": "Task"},
                            "resolutiondate": "2026-09-20T10:04:00.000+0300",
                        },
                    },
                    {
                        "key": "APPCE-8",
                        "fields": {
                            "summary": "No date",
                            "status": {"name": "Done"},
                            "issuetype": {"name": "Bug"},
                        },
                    },
                ]
            }
        )

    monkeypatch.setattr("src.integrations.jira.client.requests.get", fake_get)

    result = get_jira_recently_done(
        "APPCE", "user@example.com", "secret-token", "https://example.atlassian.net"
    )

    assert "statusCategory = Done" in seen["jql"] and 'project = "APPCE"' in seen["jql"]
    assert "resolutiondate" in seen["fields"]
    assert result == {
        "issues": [
            "APPCE-7 · Task · Done · 2026-09-20 · Ship it",
            "APPCE-8 · Bug · Done · no date · No date",
        ],
        "truncated": False,
    }


def test_get_jira_recently_done_is_capped_and_says_when_there_is_more(monkeypatch):
    """When more done issues exist than DEFAULT_LIMIT, the result is capped and marked truncated."""
    _serving(monkeypatch, [_issue(n) for n in range(1, DEFAULT_LIMIT + 5)])

    result = get_jira_recently_done("APPCE", "u@example.com", "t", "https://example.atlassian.net")

    assert len(result["issues"]) == DEFAULT_LIMIT and result["truncated"] is True


def test_a_bad_key_never_reaches_jira_when_asking_for_done_issues(monkeypatch):
    """An invalid project key is rejected before any request is made to Jira for done issues."""

    def no_network(*args, **kwargs):
        """Fail the test if a request is made at all."""
        raise AssertionError("a bad key must not reach Jira")

    monkeypatch.setattr("src.integrations.jira.client.requests.get", no_network)

    with pytest.raises(ValueError):
        get_jira_recently_done(
            'X" OR project != "', "u@example.com", "t", "https://example.atlassian.net"
        )


# The server calls whatever address the user typed, sending the
# credentials along, so only a Jira Cloud address is accepted.
BAD_ADDRESSES = [
    "http://example.atlassian.net",  # not https
    "https://169.254.169.254",  # the metadata server
    "https://localhost",
    "https://evil.com",
    "https://example.atlassian.net.evil.com",  # only looks like it
    "https://evil.com/example.atlassian.net",
    "https://user@example.atlassian.net",  # credentials in the address
    "https://example.atlassian.net:8443",  # another port
    "https://example.atlassian.net/some/path",
    "https://example.atlassian.net?x=1",
    "https://atlassian.net",  # no workspace name
    "https://-bad.atlassian.net",
    "file:///etc/passwd",
    "example.atlassian.net",  # no scheme
    "",
]


@pytest.mark.parametrize("base_url", BAD_ADDRESSES)
def test_validate_jira_credentials_refuses_an_address_that_is_not_jira_cloud(monkeypatch, base_url):
    """An address that isn't a plain https Jira Cloud URL is rejected without ever making a request."""
    calls = []
    monkeypatch.setattr(
        "src.integrations.jira.client.requests.get",
        lambda *args, **kwargs: calls.append(args) or FakeResponse(),
    )

    with pytest.raises(ValueError):
        validate_jira_credentials("user@example.com", "secret-token", base_url)

    assert calls == []  # nothing was sent anywhere


@pytest.mark.parametrize(
    "base_url",
    [
        "https://example.atlassian.net",
        "https://Example.Atlassian.net/",
        "https://my-team2.atlassian.net",
    ],
)
def test_validate_jira_credentials_accepts_a_jira_cloud_address(monkeypatch, base_url):
    """A plain https Jira Cloud address, in any case and with or without a trailing slash, is accepted."""
    monkeypatch.setattr(
        "src.integrations.jira.client.requests.get", lambda *args, **kwargs: FakeResponse()
    )

    validate_jira_credentials("user@example.com", "secret-token", base_url)


def test_the_requests_never_follow_a_redirect(monkeypatch):
    """Both validate_jira_credentials and get_jira_status disable redirect following."""
    seen = []

    def fake_get(url, **kwargs):
        """Record whether the caller allowed redirects."""
        seen.append(kwargs.get("allow_redirects"))
        return FakeResponse()

    monkeypatch.setattr("src.integrations.jira.client.requests.get", fake_get)

    validate_jira_credentials("user@example.com", "secret-token", "https://example.atlassian.net")
    get_jira_status("APPCE", "user@example.com", "secret-token", "https://example.atlassian.net")

    assert seen == [False, False]


def test_a_saved_bad_address_is_not_called_when_reading_the_status(monkeypatch):
    """A previously saved base URL that is not a valid Jira Cloud address is rejected before any request is made."""
    calls = []
    monkeypatch.setattr(
        "src.integrations.jira.client.requests.get",
        lambda *args, **kwargs: calls.append(args) or FakeResponse(),
    )

    with pytest.raises(ValueError):
        get_jira_status("APPCE", "user@example.com", "secret-token", "https://169.254.169.254")

    assert calls == []


@pytest.mark.parametrize("status", [302, 403, 404, 500])
def test_validate_jira_credentials_turns_any_other_failure_into_a_value_error(monkeypatch, status):
    """Any non-200 status from Jira, not just 401, is turned into a ValueError."""
    monkeypatch.setattr(
        "src.integrations.jira.client.requests.get",
        lambda *args, **kwargs: FakeResponse(status=status),
    )

    with pytest.raises(ValueError):
        validate_jira_credentials(
            "user@example.com", "secret-token", "https://example.atlassian.net"
        )
