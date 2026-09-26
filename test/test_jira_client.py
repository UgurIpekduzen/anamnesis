import pytest
import requests

from src.jira_client import (
    DEFAULT_LIMIT,
    MAX_SUMMARY_CHARS,
    get_jira_recently_done,
    get_jira_status,
    validate_jira_credentials,
    validate_project_key,
)


class FakeResponse:
    def __init__(self, payload=None, status=200):
        self._payload = payload or {}
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"status {self.status_code}")

    def json(self):
        return self._payload


def test_get_jira_status_maps_the_expected_fields(monkeypatch):
    def fake_get(url, auth, params, timeout):
        assert url == "https://example.atlassian.net/rest/api/3/search/jql"
        assert auth == ("user@example.com", "secret-token")
        assert 'project = "APPCE"' in params["jql"]
        return FakeResponse(
            {
                "issues": [
                    {
                        "key": "APPCE-1",
                        "fields": {"summary": "Fix bug", "status": {"name": "In Progress"}, "issuetype": {"name": "Bug"}},
                    }
                ]
            }
        )

    monkeypatch.setattr("src.jira_client.requests.get", fake_get)

    result = get_jira_status("APPCE", "user@example.com", "secret-token", "https://example.atlassian.net")

    assert result == {"issues": ["APPCE-1 · Bug · In Progress · Fix bug"], "truncated": False}


def _issue(number, summary="Fix bug"):
    return {
        "key": f"APPCE-{number}",
        "fields": {"summary": summary, "status": {"name": "To Do"}, "issuetype": {"name": "Task"}},
    }


def _serving(monkeypatch, issues):
    seen = {}

    def fake_get(url, auth, params, timeout):
        seen["params"] = params
        # Like Jira: never more than was asked for.
        return FakeResponse({"issues": issues[: params["maxResults"]]})

    monkeypatch.setattr("src.jira_client.requests.get", fake_get)
    return seen


def test_only_the_most_recent_issues_up_to_the_limit_are_returned(monkeypatch):
    _serving(monkeypatch, [_issue(n) for n in range(1, 41)])

    result = get_jira_status("APPCE", "u@example.com", "t", "https://example.atlassian.net")

    assert len(result["issues"]) == DEFAULT_LIMIT
    assert result["issues"][0].startswith("APPCE-1 ")
    assert result["truncated"] is True


def test_it_asks_jira_for_one_more_than_the_limit_only_to_detect_more(monkeypatch):
    seen = _serving(monkeypatch, [_issue(n) for n in range(1, 41)])

    get_jira_status("APPCE", "u@example.com", "t", "https://example.atlassian.net", limit=5)

    assert seen["params"]["maxResults"] == 6


def test_exactly_the_limit_is_not_reported_as_truncated(monkeypatch):
    _serving(monkeypatch, [_issue(n) for n in range(1, DEFAULT_LIMIT + 1)])

    result = get_jira_status("APPCE", "u@example.com", "t", "https://example.atlassian.net")

    assert len(result["issues"]) == DEFAULT_LIMIT
    assert result["truncated"] is False


def test_a_project_with_no_open_issues_returns_an_empty_list(monkeypatch):
    _serving(monkeypatch, [])

    assert get_jira_status("APPCE", "u@example.com", "t", "https://example.atlassian.net") == {
        "issues": [],
        "truncated": False,
    }


def test_a_long_summary_is_cut_off_with_an_ellipsis(monkeypatch):
    _serving(monkeypatch, [_issue(1, summary="x" * 500)])

    line = get_jira_status("APPCE", "u@example.com", "t", "https://example.atlassian.net")["issues"][0]

    summary = line.split(" · ", 3)[3]
    assert len(summary) == MAX_SUMMARY_CHARS
    assert summary.endswith("…")


def test_a_summary_at_the_limit_is_left_alone(monkeypatch):
    _serving(monkeypatch, [_issue(1, summary="y" * MAX_SUMMARY_CHARS)])

    line = get_jira_status("APPCE", "u@example.com", "t", "https://example.atlassian.net")["issues"][0]

    assert line.endswith("y" * MAX_SUMMARY_CHARS)
    assert "…" not in line


def test_get_jira_status_strips_a_trailing_slash_from_the_base_url(monkeypatch):
    def fake_get(url, auth, params, timeout):
        assert url == "https://example.atlassian.net/rest/api/3/search/jql"
        return FakeResponse({"issues": []})

    monkeypatch.setattr("src.jira_client.requests.get", fake_get)

    get_jira_status("APPCE", "user@example.com", "secret-token", "https://example.atlassian.net/")


def test_validate_jira_credentials_accepts_a_successful_response(monkeypatch):
    monkeypatch.setattr("src.jira_client.requests.get", lambda url, auth, timeout: FakeResponse())

    validate_jira_credentials("user@example.com", "secret-token", "https://example.atlassian.net")


def test_validate_jira_credentials_rejects_a_401(monkeypatch):
    monkeypatch.setattr("src.jira_client.requests.get", lambda url, auth, timeout: FakeResponse(status=401))

    with pytest.raises(ValueError):
        validate_jira_credentials("user@example.com", "wrong-token", "https://example.atlassian.net")


def test_validate_jira_credentials_wraps_a_connection_failure(monkeypatch):
    def fake_get(url, auth, timeout):
        raise requests.ConnectionError("no such host")

    monkeypatch.setattr("src.jira_client.requests.get", fake_get)

    with pytest.raises(ValueError):
        validate_jira_credentials("user@example.com", "secret-token", "https://not-a-real-host.invalid")


@pytest.mark.parametrize("key", ["APPCE", "APP2026", "AB", "A_1", "X" * 50])
def test_a_plain_project_key_is_accepted(key):
    validate_project_key(key)


@pytest.mark.parametrize(
    "key",
    [
        "",
        "a",
        "appce",  # lowercase
        "A",  # a single character
        "1ABC",  # starts with a digit
        "AB CD",
        "AB-CD",
        'X" OR project != "',  # would change the meaning of the query it is put into
        "X\nY",
        "X" * 51,
        None,
        123,
    ],
)
def test_anything_that_is_not_a_plain_project_key_is_rejected(key):
    with pytest.raises(ValueError):
        validate_project_key(key)


def test_a_bad_key_saved_earlier_never_reaches_jira(monkeypatch):
    def unexpected(*args, **kwargs):
        raise AssertionError("no request may be made with an invalid key")

    monkeypatch.setattr("src.jira_client.requests.get", unexpected)

    with pytest.raises(ValueError):
        get_jira_status('X" OR project != "', "u@example.com", "t", "https://example.atlassian.net")


def test_get_jira_recently_done_asks_for_done_issues_and_shows_the_resolution_date(monkeypatch):
    seen = {}

    def fake_get(url, auth, params, timeout):
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
                        "fields": {"summary": "No date", "status": {"name": "Done"}, "issuetype": {"name": "Bug"}},
                    },
                ]
            }
        )

    monkeypatch.setattr("src.jira_client.requests.get", fake_get)

    result = get_jira_recently_done("APPCE", "user@example.com", "secret-token", "https://example.atlassian.net")

    assert "statusCategory = Done" in seen["jql"] and 'project = "APPCE"' in seen["jql"]
    assert "resolutiondate" in seen["fields"]
    assert result == {
        "issues": ["APPCE-7 · Task · Done · 2026-09-20 · Ship it", "APPCE-8 · Bug · Done · no date · No date"],
        "truncated": False,
    }


def test_get_jira_recently_done_is_capped_and_says_when_there_is_more(monkeypatch):
    _serving(monkeypatch, [_issue(n) for n in range(1, DEFAULT_LIMIT + 5)])

    result = get_jira_recently_done("APPCE", "u@example.com", "t", "https://x")

    assert len(result["issues"]) == DEFAULT_LIMIT and result["truncated"] is True


def test_a_bad_key_never_reaches_jira_when_asking_for_done_issues(monkeypatch):
    def no_network(*args, **kwargs):
        raise AssertionError("a bad key must not reach Jira")

    monkeypatch.setattr("src.jira_client.requests.get", no_network)

    with pytest.raises(ValueError):
        get_jira_recently_done('X" OR project != "', "u@example.com", "t", "https://x")
