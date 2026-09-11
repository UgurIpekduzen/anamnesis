import pytest

from src.jira_client import _auth, _base_url


def test_base_url_strips_trailing_slash(monkeypatch):
    monkeypatch.setenv("JIRA_BASE_URL", "https://example.atlassian.net/")
    assert _base_url() == "https://example.atlassian.net"


def test_base_url_raises_when_unset(monkeypatch):
    monkeypatch.delenv("JIRA_BASE_URL", raising=False)
    with pytest.raises(RuntimeError):
        _base_url()


def test_auth_returns_email_and_token(monkeypatch):
    monkeypatch.setenv("JIRA_EMAIL", "user@example.com")
    monkeypatch.setenv("JIRA_API_TOKEN", "secret-token")
    assert _auth() == ("user@example.com", "secret-token")


def test_auth_raises_when_missing(monkeypatch):
    monkeypatch.delenv("JIRA_EMAIL", raising=False)
    monkeypatch.delenv("JIRA_API_TOKEN", raising=False)
    with pytest.raises(RuntimeError):
        _auth()
