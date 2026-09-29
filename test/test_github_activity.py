"""Tests for fetching and summarizing a linked GitHub repo's pull requests and issues."""

import pytest

from src.integrations.github import activity as github_activity


class FakeResponse:
    """A stand-in for a requests.Response, serving a fixed JSON payload and
    status code."""

    def __init__(self, payload, status=200):
        """Store the fake JSON payload and status code."""
        self._payload = payload
        self.status_code = status

    def raise_for_status(self):
        """Raise like a real response would for a 4xx/5xx status code."""
        if self.status_code >= 400:
            raise RuntimeError(f"status {self.status_code}")

    def json(self):
        """Return the fixed payload this response was built with."""
        return self._payload


@pytest.fixture(autouse=True)
def connected_tenant(monkeypatch):
    """Stub the tenant lookup and token decryption so every test sees a
    tenant with a linked repo and a valid GitHub token."""
    monkeypatch.setattr(github_activity, "get_owned_tenant", lambda tenant_id, owner_uid: {"github_repo": "owner/repo"})
    monkeypatch.setattr(github_activity, "get_decrypted_token", lambda owner_uid: "github_pat_x")


def test_fetch_recent_pull_requests_maps_the_expected_fields(monkeypatch):
    """fetch_recent_pull_requests() calls the pulls endpoint with a bearer
    token and maps the GitHub response fields to the expected shape."""
    def fake_get(url, params, headers, timeout):
        """Assert the pulls endpoint and auth header are correct, then return one PR."""
        assert url == "https://api.github.com/repos/owner/repo/pulls"
        assert headers["Authorization"] == "Bearer github_pat_x"
        return FakeResponse(
            [{"number": 1, "title": "Fix bug", "body": "Because X", "state": "open", "updated_at": "t", "html_url": "u"}]
        )

    monkeypatch.setattr(github_activity.requests, "get", fake_get)

    result = github_activity.fetch_recent_pull_requests("owner-uid", "tenant-1")

    assert result == [
        {
            "number": 1,
            "title": "Fix bug",
            "body": "Because X",
            "state": "open",
            "merged_at": None,
            "updated_at": "t",
            "url": "u",
        }
    ]


def test_fetch_recent_issues_filters_out_pull_requests(monkeypatch):
    """fetch_recent_issues() drops entries the issues endpoint returns that
    are actually pull requests (they carry a "pull_request" key)."""
    def fake_get(url, params, headers, timeout):
        """Return one real issue and one PR-flagged entry from the issues endpoint."""
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
    """A PR body longer than MAX_BODY_CHARS is cut to that length plus a
    trailing "…" marker."""
    long_body = "x" * (github_activity.MAX_BODY_CHARS + 500)

    def fake_get(url, params, headers, timeout):
        """Return one PR with an oversized body."""
        return FakeResponse(
            [{"number": 1, "title": "t", "body": long_body, "state": "open", "updated_at": "t", "html_url": "u"}]
        )

    monkeypatch.setattr(github_activity.requests, "get", fake_get)

    result = github_activity.fetch_recent_pull_requests("owner-uid", "tenant-1")

    assert len(result[0]["body"]) == github_activity.MAX_BODY_CHARS + 1  # + the "…" marker
    assert result[0]["body"].endswith("…")


def test_a_missing_body_becomes_an_empty_string(monkeypatch):
    """A PR with a null body maps to an empty string, not None."""
    def fake_get(url, params, headers, timeout):
        """Return one PR whose body is null."""
        return FakeResponse([{"number": 1, "title": "t", "body": None, "state": "open", "updated_at": "t", "html_url": "u"}])

    monkeypatch.setattr(github_activity.requests, "get", fake_get)

    result = github_activity.fetch_recent_pull_requests("owner-uid", "tenant-1")

    assert result[0]["body"] == ""


def test_fetching_without_a_linked_repo_is_an_error(monkeypatch):
    """fetch_recent_pull_requests() raises ValueError when the tenant has no
    linked GitHub repo."""
    monkeypatch.setattr(github_activity, "get_owned_tenant", lambda tenant_id, owner_uid: {})

    with pytest.raises(ValueError):
        github_activity.fetch_recent_pull_requests("owner-uid", "tenant-1")


def test_fetching_without_a_github_connection_is_an_error(monkeypatch):
    """fetch_recent_pull_requests() raises ValueError when the owner has no
    decrypted GitHub token."""
    monkeypatch.setattr(github_activity, "get_decrypted_token", lambda owner_uid: None)

    with pytest.raises(ValueError):
        github_activity.fetch_recent_pull_requests("owner-uid", "tenant-1")


def test_get_github_status_only_requests_open_items(monkeypatch):
    """get_github_status() requests only open pull requests and open issues."""
    seen_states = []

    def fake_get(url, params, headers, timeout):
        """Record the requested "state" filter and return no items."""
        seen_states.append(params["state"])
        return FakeResponse([])

    monkeypatch.setattr(github_activity.requests, "get", fake_get)

    github_activity.get_github_status("owner-uid", "tenant-1")

    assert seen_states == ["open", "open"]


def test_get_github_status_strips_the_body_from_every_item(monkeypatch):
    """get_github_status() drops the body field from every pull request and
    issue it returns."""
    def fake_get(url, params, headers, timeout):
        """Return one PR and one issue, each with a body."""
        if url.endswith("/pulls"):
            return FakeResponse(
                [{"number": 1, "title": "A PR", "body": "secret instructions", "state": "open", "updated_at": "t", "html_url": "u1"}]
            )
        return FakeResponse(
            [{"number": 2, "title": "An issue", "body": "more text", "state": "open", "updated_at": "t", "html_url": "u2"}]
        )

    monkeypatch.setattr(github_activity.requests, "get", fake_get)

    result = github_activity.get_github_status("owner-uid", "tenant-1")

    assert result == {
        "pull_requests": [{"number": 1, "title": "A PR", "state": "open", "updated_at": "t", "url": "u1"}],
        "issues": [{"number": 2, "title": "An issue", "state": "open", "updated_at": "t", "url": "u2"}],
    }
    assert "body" not in result["pull_requests"][0]
    assert "body" not in result["issues"][0]


def _pr(number, title="A PR", merged_at=None, updated_at="2026-09-20T10:00:00Z"):
    return {
        "number": number,
        "title": title,
        "body": "secret instructions",
        "state": "closed",
        "merged_at": merged_at,
        "updated_at": updated_at,
        "html_url": f"u{number}",
    }


def _serving_history(monkeypatch, pulls, issues):
    seen = []

    def fake_get(url, params, headers, timeout):
        """Record the call and return up to per_page rows from pulls or issues."""
        seen.append((url, params))
        rows = pulls if url.endswith("/pulls") else issues
        return FakeResponse(rows[: params["per_page"]])

    monkeypatch.setattr(github_activity.requests, "get", fake_get)
    return seen


def test_get_github_history_asks_for_closed_items_and_returns_compact_lines_without_bodies(monkeypatch):
    """get_github_history() requests closed items and returns them as
    compact "#n · state · date · title" lines with no body text."""
    seen = _serving_history(
        monkeypatch,
        pulls=[_pr(1, "Add caching", merged_at="2026-09-21T09:00:00Z"), _pr(2, "Abandoned idea")],
        issues=[{**_pr(5, "Login fails"), "state": "closed"}, {**_pr(6, "Not an issue"), "pull_request": {}}],
    )

    result = github_activity.get_github_history("owner-uid", "tenant-1")

    assert all(params["state"] == "closed" for _, params in seen)
    assert result == {
        "pull_requests": ["#1 · merged · 2026-09-21 · Add caching", "#2 · closed · 2026-09-20 · Abandoned idea"],
        "issues": ["#5 · closed · 2026-09-20 · Login fails"],
        "truncated": False,
    }
    assert "secret instructions" not in str(result)


def test_get_github_history_is_capped_and_says_when_there_is_more(monkeypatch):
    """get_github_history() caps its pull-request lines at HISTORY_LIMIT and
    sets truncated=True when more items were available."""
    seen = _serving_history(monkeypatch, pulls=[_pr(n) for n in range(1, 40)], issues=[])

    result = github_activity.get_github_history("owner-uid", "tenant-1")

    assert len(result["pull_requests"]) == github_activity.HISTORY_LIMIT
    assert result["truncated"] is True
    # One more than shown, only to learn whether there is more.
    assert seen[0][1]["per_page"] == github_activity.HISTORY_LIMIT + 1


def test_get_github_history_cuts_a_long_title(monkeypatch):
    """A long PR title is cut short with a "…" marker in the history line."""
    _serving_history(monkeypatch, pulls=[_pr(1, "x" * 300)], issues=[])

    (line,) = github_activity.get_github_history("owner-uid", "tenant-1")["pull_requests"]

    assert line.endswith("…") and len(line) < 130
