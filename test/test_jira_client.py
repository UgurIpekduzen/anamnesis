import pytest
import requests

from src.jira_client import get_jira_status, validate_jira_credentials


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

    assert result == [{"key": "APPCE-1", "summary": "Fix bug", "status": "In Progress", "issue_type": "Bug"}]


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
