from datetime import datetime, timezone

import pytest

from src.integrations.github import polling as github_polling


def _pr(number, title="t", body="b", updated_at="2026-01-02T00:00:00Z"):
    return {"number": number, "title": title, "body": body, "state": "open", "updated_at": updated_at, "url": f"u{number}"}


@pytest.fixture
def wired(monkeypatch):
    state = {
        "tenant": {"github_polled_at": None},
        "prs": [],
        "issues": [],
        "extracted": {},
        "created": [],
        "marked": [],
        "pending_urls": set(),
        "extract_calls": [],
    }

    monkeypatch.setattr(github_polling, "get_owned_tenant", lambda tenant_id, owner_uid: state["tenant"])
    monkeypatch.setattr(github_polling, "fetch_recent_pull_requests", lambda owner_uid, tenant_id: state["prs"])
    monkeypatch.setattr(github_polling, "fetch_recent_issues", lambda owner_uid, tenant_id: state["issues"])

    def fake_extract(title, body, kind, owner_uid):
        state["extract_calls"].append(title)
        return state["extracted"].get(title, [])

    monkeypatch.setattr(github_polling, "extract_facts", fake_extract)
    monkeypatch.setattr(
        github_polling, "has_pending_fact_for_source", lambda tenant_id, url: url in state["pending_urls"]
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


def test_an_item_that_already_has_a_pending_fact_is_not_extracted_again(wired):
    wired["prs"] = [_pr(1, title="staged"), _pr(2, title="new")]
    wired["extracted"] = {"staged": [{"content": "a", "category": "decision"}], "new": [{"content": "b", "category": "decision"}]}
    wired["pending_urls"] = {"u1"}

    count = github_polling.poll_tenant_github_activity("owner", "tenant-1")

    assert count == 1
    assert wired["extract_calls"] == ["new"]


def test_running_the_same_poll_twice_does_not_stage_duplicates(wired, monkeypatch):
    wired["prs"] = [_pr(1, title="t1")]
    wired["extracted"] = {"t1": [{"content": "a", "category": "decision"}]}
    # A retried scheduler run sees what the first one staged.
    monkeypatch.setattr(
        github_polling,
        "create_pending_fact",
        lambda tenant_id, content, category, source, source_url, owner_uid: (
            wired["created"].append(source_url),
            wired["pending_urls"].add(source_url),
        ),
    )

    github_polling.poll_tenant_github_activity("owner", "tenant-1")
    github_polling.poll_tenant_github_activity("owner", "tenant-1")

    assert wired["created"] == ["u1"]
    assert wired["extract_calls"] == ["t1"]


def test_extractions_stop_at_the_cap_and_the_poll_is_still_marked_done(wired, capsys, log_lines):
    wired["prs"] = [_pr(n, title=f"t{n}") for n in range(1, 6)]

    github_polling.poll_tenant_github_activity("owner", "tenant-1", max_extractions=3)

    assert wired["extract_calls"] == ["t1", "t2", "t3"]
    assert wired["marked"] == ["tenant-1"]
    (entry,) = log_lines(capsys.readouterr().out)
    assert entry == {
        "severity": "WARNING",
        "event": "github_poll_cap_hit",
        "tenant_id": "tenant-1",
        "cap": 3,
        "dropped": 2,
    }


def test_the_cap_is_shared_between_pull_requests_and_issues(wired):
    wired["prs"] = [_pr(n, title=f"pr{n}") for n in range(1, 3)]
    wired["issues"] = [_pr(n + 10, title=f"issue{n}") for n in range(1, 4)]

    github_polling.poll_tenant_github_activity("owner", "tenant-1", max_extractions=3)

    assert wired["extract_calls"] == ["pr1", "pr2", "issue1"]


def test_items_that_already_have_a_pending_fact_do_not_use_up_the_cap(wired):
    wired["prs"] = [_pr(n, title=f"t{n}") for n in range(1, 5)]
    wired["pending_urls"] = {"u1", "u2"}

    github_polling.poll_tenant_github_activity("owner", "tenant-1", max_extractions=2)

    assert wired["extract_calls"] == ["t3", "t4"]


def test_items_older_than_the_last_poll_do_not_use_up_the_cap(wired):
    wired["tenant"]["github_polled_at"] = datetime(2026, 6, 1, tzinfo=timezone.utc)
    wired["prs"] = [
        _pr(1, title="old1", updated_at="2026-01-01T00:00:00Z"),
        _pr(2, title="old2", updated_at="2026-01-01T00:00:00Z"),
        _pr(3, title="fresh", updated_at="2026-07-01T00:00:00Z"),
    ]

    github_polling.poll_tenant_github_activity("owner", "tenant-1", max_extractions=1)

    assert wired["extract_calls"] == ["fresh"]


def test_the_default_cap_is_applied_when_none_is_passed(wired):
    over = github_polling.MAX_EXTRACTIONS_PER_POLL + 5
    wired["prs"] = [_pr(n, title=f"t{n}") for n in range(1, over + 1)]

    github_polling.poll_tenant_github_activity("owner", "tenant-1")

    assert len(wired["extract_calls"]) == github_polling.MAX_EXTRACTIONS_PER_POLL


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


def test_poll_all_tenants_logs_one_structured_summary_line(all_wired, capsys, log_lines):
    all_wired["tenants"] = [
        {"owner_uid": "owner-a", "tenant_id": "boom"},
        {"owner_uid": "owner-b", "tenant_id": "t2"},
    ]

    github_polling.poll_all_tenants()

    # A failed tenant makes it an ERROR, so a log-based alert can fire on it.
    assert log_lines(capsys.readouterr().out)[-1] == {
        "severity": "ERROR",
        "event": "github_poll",
        "polled": 1,
        "created": 3,
        "error_count": 1,
        "failed_tenants": ["boom"],
    }


def test_the_summary_line_never_includes_error_text(all_wired, monkeypatch, capsys):
    def leaky_poll(owner_uid, tenant_id, max_extractions=None):
        raise RuntimeError("401 for token ghp_SECRET123")

    monkeypatch.setattr(github_polling, "poll_tenant_github_activity", leaky_poll)
    all_wired["tenants"] = [{"owner_uid": "owner-a", "tenant_id": "t1"}]

    result = github_polling.poll_all_tenants()

    assert "ghp_SECRET123" not in capsys.readouterr().out
    # The caller still gets the message, only the log line is scrubbed.
    assert "ghp_SECRET123" in result["errors"][0]["error"]


def test_the_summary_line_is_logged_even_when_there_is_nothing_to_poll(all_wired, capsys, log_lines):
    github_polling.poll_all_tenants()

    assert log_lines(capsys.readouterr().out)[-1] == {
        "severity": "INFO",
        "event": "github_poll",
        "polled": 0,
        "created": 0,
        "error_count": 0,
        "failed_tenants": [],
    }
