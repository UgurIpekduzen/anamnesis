"""Integration tests for GitHub activity polling and its pending-fact staging."""

import uuid

import pytest

from src.integrations.github import polling as github_polling
from src.facts.pending_facts import list_pending_facts
from src.projects.tenants import add_tenant, delete_tenant

OWNER_UID = "test-owner@example.com"


@pytest.fixture
def tenant_id():
    """Create a real tenant for the poll to write into, and delete it afterwards."""
    tenant_id = add_tenant(f"Polling Test {uuid.uuid4().hex[:8]}", OWNER_UID)
    yield tenant_id
    delete_tenant(tenant_id, OWNER_UID)


def _pr(number):
    return {
        "number": number,
        "title": f"PR {number}",
        "body": "body",
        "state": "open",
        "updated_at": "2026-01-02T00:00:00Z",
        "url": f"https://github.com/o/r/pull/{number}",
    }


def test_polling_twice_stages_each_item_once(tenant_id, monkeypatch):
    """Polling the same GitHub activity twice stages each pull request as a pending fact only once."""
    # Only GitHub and the LLM are stubbed; the pending-fact writes and the
    # duplicate check hit the real (emulated) Firestore.
    monkeypatch.setattr(
        github_polling, "fetch_recent_pull_requests", lambda owner_uid, tid: [_pr(1), _pr(2)]
    )
    monkeypatch.setattr(github_polling, "fetch_recent_issues", lambda owner_uid, tid: [])
    monkeypatch.setattr(
        github_polling,
        "extract_facts",
        lambda title, body, kind, owner_uid: [
            {"content": f"Fact from {title}", "category": "decision"}
        ],
    )
    # A retried scheduler run: the poll timestamp hasn't advanced, so both
    # items look new again and only the duplicate check can stop them.
    monkeypatch.setattr(github_polling, "mark_github_polled", lambda tid, owner_uid: None)

    first = github_polling.poll_tenant_github_activity(OWNER_UID, tenant_id)
    second = github_polling.poll_tenant_github_activity(OWNER_UID, tenant_id)

    assert (first, second) == (2, 0)
    assert sorted(f["source_url"] for f in list_pending_facts(tenant_id, OWNER_UID)) == [
        "https://github.com/o/r/pull/1",
        "https://github.com/o/r/pull/2",
    ]
