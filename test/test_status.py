import pytest
import requests

import src.status as status


@pytest.fixture
def linked(monkeypatch):
    """A project linked to both services, with both accounts connected."""
    monkeypatch.setattr(
        status, "get_owned_tenant", lambda tenant_id, owner_uid: {"jira_project_key": "APPCE", "github_repo": "o/r"}
    )
    monkeypatch.setattr(
        status,
        "get_jira_credentials",
        lambda owner_uid: {"email": "u@example.com", "token": "secret", "base_url": "https://x.atlassian.net/"},
    )
    monkeypatch.setattr(status, "has_github_connection", lambda owner_uid: True)


def test_jira_issues_are_split_into_fields_and_linked_to_the_issue(linked, monkeypatch):
    monkeypatch.setattr(
        status,
        "get_jira_status",
        lambda key, **credentials: {"issues": ["APPCE-7 · Bug · In Progress · Fix the login · again"], "truncated": True},
    )

    result = status.get_project_jira_status("t", "o")

    assert result == {
        "state": "ok",
        "project_key": "APPCE",
        "issues": [
            {
                "key": "APPCE-7",
                "type": "Bug",
                "status": "In Progress",
                "summary": "Fix the login · again",
                "url": "https://x.atlassian.net/browse/APPCE-7",
            }
        ],
        "truncated": True,
    }


def test_a_project_with_no_jira_key_is_not_linked(monkeypatch):
    monkeypatch.setattr(status, "get_owned_tenant", lambda tenant_id, owner_uid: {})

    assert status.get_project_jira_status("t", "o") == {"state": "not_linked"}
    assert status.get_project_github_status("t", "o") == {"state": "not_linked"}


def test_no_jira_account_is_not_connected(linked, monkeypatch):
    monkeypatch.setattr(status, "get_jira_credentials", lambda owner_uid: None)

    assert status.get_project_jira_status("t", "o") == {"state": "not_connected"}


def test_a_saved_token_that_cannot_be_read_says_to_reconnect(linked, monkeypatch):
    def unreadable(owner_uid):
        raise ValueError("The saved token can't be decrypted. Reconnect it in Settings.")

    monkeypatch.setattr(status, "get_jira_credentials", unreadable)

    assert status.get_project_jira_status("t", "o") == {
        "state": "error",
        "message": "The saved token can't be decrypted. Reconnect it in Settings.",
    }


def test_a_failing_jira_call_is_an_error_without_the_libraries_text(linked, monkeypatch):
    response = requests.Response()
    response.status_code = 401

    def rejected(key, **credentials):
        raise requests.HTTPError("401 for https://x.atlassian.net/?token=SECRET", response=response)

    monkeypatch.setattr(status, "get_jira_status", rejected)

    result = status.get_project_jira_status("t", "o")

    assert result == {"state": "error", "message": "Jira rejected the saved credentials. Reconnect it in Settings."}
    assert "SECRET" not in str(result)


def test_a_network_failure_is_reported_plainly(linked, monkeypatch):
    def down(key, **credentials):
        raise requests.ConnectionError("dns failure for host x")

    monkeypatch.setattr(status, "get_jira_status", down)

    assert status.get_project_jira_status("t", "o") == {"state": "error", "message": "Couldn't reach Jira."}


def test_github_returns_numbers_titles_and_links_only(linked, monkeypatch):
    monkeypatch.setattr(
        status,
        "get_github_status",
        lambda owner_uid, tenant_id: {
            "pull_requests": [{"number": 1, "title": "Add cache", "state": "open", "updated_at": "t", "url": "u1"}],
            "issues": [{"number": 2, "title": "Login fails", "state": "open", "updated_at": "t", "url": "u2"}],
        },
    )

    assert status.get_project_github_status("t", "o") == {
        "state": "ok",
        "repo": "o/r",
        "pull_requests": [{"number": 1, "title": "Add cache", "url": "u1"}],
        "issues": [{"number": 2, "title": "Login fails", "url": "u2"}],
    }


def test_no_github_account_is_not_connected(linked, monkeypatch):
    monkeypatch.setattr(status, "has_github_connection", lambda owner_uid: False)

    assert status.get_project_github_status("t", "o") == {"state": "not_connected"}


def test_a_failing_github_call_is_an_error(linked, monkeypatch):
    def broken(owner_uid, tenant_id):
        raise RuntimeError("boom with a token ghp_SECRET")

    monkeypatch.setattr(status, "get_github_status", broken)

    result = status.get_project_github_status("t", "o")

    assert result == {"state": "error", "message": "Couldn't read GitHub."}


def test_someone_elses_project_is_refused(monkeypatch):
    def not_yours(tenant_id, owner_uid):
        raise PermissionError("No project")

    monkeypatch.setattr(status, "get_owned_tenant", not_yours)

    with pytest.raises(PermissionError):
        status.get_project_jira_status("t", "o")
    with pytest.raises(PermissionError):
        status.get_project_github_status("t", "o")


@pytest.mark.parametrize(
    "code, service, expected",
    [
        (403, "Jira", "Jira refused the request (permissions or a rate limit)."),
        (404, "Jira", "Jira couldn't find the project."),
        (404, "GitHub", "GitHub couldn't find the repo, or the token has no access to it."),
        (500, "GitHub", "GitHub answered with HTTP 500."),
    ],
)
def test_common_http_failures_say_what_to_check(code, service, expected):
    response = requests.Response()
    response.status_code = code

    assert status._failure(service, requests.HTTPError("x", response=response)) == expected
