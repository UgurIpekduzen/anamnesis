from datetime import datetime, timezone

import pytest

from src import github_polling


def _pr(number, title="t", body="b", updated_at="2026-01-02T00:00:00Z"):
    return {"number": number, "title": title, "body": body, "state": "open", "updated_at": updated_at, "url": f"u{number}"}


@pytest.fixture
def wired(monkeypatch):
    state = {"tenant": {"github_polled_at": None}, "prs": [], "issues": [], "extracted": {}, "created": [], "marked": []}

    monkeypatch.setattr(github_polling, "get_owned_tenant", lambda tenant_id, owner_uid: state["tenant"])
    monkeypatch.setattr(github_polling, "fetch_recent_pull_requests", lambda owner_uid, tenant_id: state["prs"])
    monkeypatch.setattr(github_polling, "fetch_recent_issues", lambda owner_uid, tenant_id: state["issues"])
    monkeypatch.setattr(
        github_polling, "extract_facts", lambda title, body, kind: state["extracted"].get(title, [])
    )
    monkeypatch.setattr(
        github_polling,
        "create_pending_fact",
        lambda tenant_id, content, category, source, source_url, owner_uid: state["created"].append(
            (content, category, source, source_url)
        ),
    )
    monkeypatch.setattr(
        github_polling, "mark_github_polled", lambda tenant_id, owner_uid: state["marked"].append(tenant_id)
    )
    return state


def test_stages_a_pending_fact_for_each_extracted_fact(wired):
    wired["prs"] = [_pr(1, title="Add caching")]
    wired["extracted"] = {"Add caching": [{"content": "Adds an LRU cache", "category": "architecture"}]}

    count = github_polling.poll_tenant_github_activity("owner", "tenant-1")

    assert count == 1
    assert wired["created"] == [("Adds an LRU cache", "architecture", "github", "u1")]


def test_an_item_with_no_extracted_facts_stages_nothing(wired):
    wired["prs"] = [_pr(1, title="Bump a dependency")]
    wired["extracted"] = {"Bump a dependency": []}

    assert github_polling.poll_tenant_github_activity("owner", "tenant-1") == 0
    assert wired["created"] == []


def test_both_pull_requests_and_issues_are_processed(wired):
    wired["prs"] = [_pr(1, title="PR one")]
    wired["issues"] = [_pr(2, title="Issue one")]
    wired["extracted"] = {
        "PR one": [{"content": "pr fact", "category": "bug"}],
        "Issue one": [{"content": "issue fact", "category": "todo"}],
    }

    count = github_polling.poll_tenant_github_activity("owner", "tenant-1")

    assert count == 2
    assert {c[0] for c in wired["created"]} == {"pr fact", "issue fact"}


def test_first_run_processes_everything_when_never_polled_before(wired):
    wired["tenant"]["github_polled_at"] = None
    wired["prs"] = [_pr(1, title="Old item", updated_at="2020-01-01T00:00:00Z")]
    wired["extracted"] = {"Old item": [{"content": "c", "category": "bug"}]}

    assert github_polling.poll_tenant_github_activity("owner", "tenant-1") == 1


def test_items_not_updated_since_the_last_poll_are_skipped(wired):
    wired["tenant"]["github_polled_at"] = datetime(2026, 6, 1, tzinfo=timezone.utc)
    wired["prs"] = [_pr(1, title="Stale item", updated_at="2026-01-01T00:00:00Z")]
    wired["extracted"] = {"Stale item": [{"content": "c", "category": "bug"}]}

    assert github_polling.poll_tenant_github_activity("owner", "tenant-1") == 0
    assert wired["created"] == []


def test_items_updated_after_the_last_poll_are_processed(wired):
    wired["tenant"]["github_polled_at"] = datetime(2026, 1, 1, tzinfo=timezone.utc)
    wired["prs"] = [_pr(1, title="Fresh item", updated_at="2026-06-01T00:00:00Z")]
    wired["extracted"] = {"Fresh item": [{"content": "c", "category": "bug"}]}

    assert github_polling.poll_tenant_github_activity("owner", "tenant-1") == 1


def test_the_tenant_is_marked_polled_after_every_run(wired):
    github_polling.poll_tenant_github_activity("owner", "tenant-1")
    assert wired["marked"] == ["tenant-1"]


@pytest.fixture
def all_wired(monkeypatch):
    state = {"tenants": [], "polled": []}

    def fake_poll(owner_uid, tenant_id):
        state["polled"].append((owner_uid, tenant_id))
        if tenant_id == "boom":
            raise RuntimeError("GitHub token expired")
        return 3

    monkeypatch.setattr(github_polling, "list_tenants_with_github_repo", lambda: state["tenants"])
    monkeypatch.setattr(github_polling, "poll_tenant_github_activity", fake_poll)
    return state


def test_poll_all_tenants_polls_every_tenant_with_a_linked_repo(all_wired):
    all_wired["tenants"] = [
        {"owner_uid": "owner-a", "tenant_id": "t1"},
        {"owner_uid": "owner-b", "tenant_id": "t2"},
    ]

    result = github_polling.poll_all_tenants()

    assert result == {"polled": 2, "created": 6, "errors": []}
    assert all_wired["polled"] == [("owner-a", "t1"), ("owner-b", "t2")]


def test_poll_all_tenants_no_op_when_nobody_has_linked_a_repo(all_wired):
    assert github_polling.poll_all_tenants() == {"polled": 0, "created": 0, "errors": []}


def test_one_tenants_failure_does_not_stop_the_others(all_wired):
    all_wired["tenants"] = [
        {"owner_uid": "owner-a", "tenant_id": "boom"},
        {"owner_uid": "owner-b", "tenant_id": "t2"},
    ]

    result = github_polling.poll_all_tenants()

    assert result["polled"] == 1
    assert result["created"] == 3
    assert result["errors"] == [{"tenant_id": "boom", "error": "GitHub token expired"}]
    # Both were still attempted, even though the first one failed.
    assert all_wired["polled"] == [("owner-a", "boom"), ("owner-b", "t2")]
