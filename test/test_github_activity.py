import pytest

from src import github_activity


class FakeResponse:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"status {self.status_code}")

    def json(self):
        return self._payload


@pytest.fixture(autouse=True)
def connected_tenant(monkeypatch):
    monkeypatch.setattr(github_activity, "get_owned_tenant", lambda tenant_id, owner_uid: {"github_repo": "owner/repo"})
    monkeypatch.setattr(github_activity, "get_decrypted_token", lambda owner_uid: "github_pat_x")


def test_fetch_recent_pull_requests_maps_the_expected_fields(monkeypatch):
    def fake_get(url, params, headers, timeout):
        assert url == "https://api.github.com/repos/owner/repo/pulls"
        assert headers["Authorization"] == "Bearer github_pat_x"
        return FakeResponse(
            [{"number": 1, "title": "Fix bug", "body": "Because X", "state": "open", "updated_at": "t", "html_url": "u"}]
        )

    monkeypatch.setattr(github_activity.requests, "get", fake_get)

    result = github_activity.fetch_recent_pull_requests("owner-uid", "tenant-1")

    assert result == [
        {"number": 1, "title": "Fix bug", "body": "Because X", "state": "open", "updated_at": "t", "url": "u"}
    ]


def test_fetch_recent_issues_filters_out_pull_requests(monkeypatch):
    def fake_get(url, params, headers, timeout):
        assert url == "https://api.github.com/repos/owner/repo/issues"
        return FakeResponse(
            [
                {"number": 1, "title": "Real issue", "body": None, "state": "open", "updated_at": "t", "html_url": "u1"},
                {
                    "number": 2,
                    "title": "This is secretly a PR",
                    "body": None,
                    "state": "open",
                    "updated_at": "t",
                    "html_url": "u2",
                    "pull_request": {"url": "..."},
                },
            ]
        )

    monkeypatch.setattr(github_activity.requests, "get", fake_get)

    result = github_activity.fetch_recent_issues("owner-uid", "tenant-1")

    assert [issue["number"] for issue in result] == [1]


def test_a_long_body_is_truncated(monkeypatch):
    long_body = "x" * (github_activity.MAX_BODY_CHARS + 500)

    def fake_get(url, params, headers, timeout):
        return FakeResponse(
            [{"number": 1, "title": "t", "body": long_body, "state": "open", "updated_at": "t", "html_url": "u"}]
        )

    monkeypatch.setattr(github_activity.requests, "get", fake_get)

    result = github_activity.fetch_recent_pull_requests("owner-uid", "tenant-1")

    assert len(result[0]["body"]) == github_activity.MAX_BODY_CHARS + 1  # + the "…" marker
    assert result[0]["body"].endswith("…")


def test_a_missing_body_becomes_an_empty_string(monkeypatch):
    def fake_get(url, params, headers, timeout):
        return FakeResponse([{"number": 1, "title": "t", "body": None, "state": "open", "updated_at": "t", "html_url": "u"}])

    monkeypatch.setattr(github_activity.requests, "get", fake_get)

    result = github_activity.fetch_recent_pull_requests("owner-uid", "tenant-1")

    assert result[0]["body"] == ""


def test_fetching_without_a_linked_repo_is_an_error(monkeypatch):
    monkeypatch.setattr(github_activity, "get_owned_tenant", lambda tenant_id, owner_uid: {})

    with pytest.raises(ValueError):
        github_activity.fetch_recent_pull_requests("owner-uid", "tenant-1")


def test_fetching_without_a_github_connection_is_an_error(monkeypatch):
    monkeypatch.setattr(github_activity, "get_decrypted_token", lambda owner_uid: None)

    with pytest.raises(ValueError):
        github_activity.fetch_recent_pull_requests("owner-uid", "tenant-1")
