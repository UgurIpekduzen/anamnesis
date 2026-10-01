"""Integration tests for the pending-fact review workflow: creation, approval, rejection, and stats."""

import uuid

import pytest

from src.facts import pending_facts as pending_facts_module
from src.facts.pending_facts import (
    approve_pending_fact,
    create_pending_fact,
    get_pending_fact_stats,
    has_pending_fact_for_source,
    list_pending_facts,
    reject_pending_fact,
)
from src.projects.tenants import add_tenant, delete_tenant

OWNER_UID = "test-owner@example.com"


@pytest.fixture
def tenant_id():
    """Create a real tenant for the pending-fact tests to use, and delete it afterwards."""
    tenant_id = add_tenant(f"Pending Facts Test {uuid.uuid4().hex[:8]}", OWNER_UID)
    yield tenant_id
    delete_tenant(tenant_id, OWNER_UID)


def test_a_created_pending_fact_is_listed(tenant_id):
    """A newly created pending fact appears in the tenant's pending-fact list with its saved fields."""
    pending_id = create_pending_fact(
        tenant_id,
        "Uses Postgres for the primary store",
        "architecture",
        "github",
        "https://github.com/o/r/pull/1",
        OWNER_UID,
    )

    listed = list_pending_facts(tenant_id, OWNER_UID)

    assert len(listed) == 1
    assert listed[0]["pending_fact_id"] == pending_id
    assert listed[0]["content"] == "Uses Postgres for the primary store"
    assert listed[0]["category"] == "architecture"
    assert listed[0]["source"] == "github"
    assert listed[0]["source_url"] == "https://github.com/o/r/pull/1"


def test_has_pending_fact_for_source_matches_only_that_url(tenant_id):
    """A pending fact is found only for the exact source URL it was created with."""
    create_pending_fact(
        tenant_id, "A fact", "architecture", "github", "https://github.com/o/r/pull/1", OWNER_UID
    )

    assert has_pending_fact_for_source(tenant_id, "https://github.com/o/r/pull/1") is True
    assert has_pending_fact_for_source(tenant_id, "https://github.com/o/r/pull/2") is False


def test_a_rejected_source_is_still_known_so_it_is_not_proposed_again(tenant_id):
    """A rejected pending fact's source URL still counts as known, so it isn't proposed again."""
    pending_id = create_pending_fact(
        tenant_id, "A fact", "architecture", "github", "https://github.com/o/r/pull/1", OWNER_UID
    )
    reject_pending_fact(tenant_id, pending_id, OWNER_UID)

    assert has_pending_fact_for_source(tenant_id, "https://github.com/o/r/pull/1") is True


def test_an_approved_source_is_still_known_too(tenant_id, monkeypatch):
    """An approved pending fact's source URL still counts as known too."""
    monkeypatch.setattr(pending_facts_module, "publish_fact", lambda *a, **k: None)
    pending_id = create_pending_fact(
        tenant_id, "A fact", "bug", "github", "https://github.com/o/r/pull/2", OWNER_UID
    )
    approve_pending_fact(tenant_id, pending_id, OWNER_UID)

    assert has_pending_fact_for_source(tenant_id, "https://github.com/o/r/pull/2") is True


def test_create_pending_fact_rejects_an_invalid_category(tenant_id):
    """Creating a pending fact with a category outside the allowed set raises ValueError."""
    with pytest.raises(ValueError):
        create_pending_fact(tenant_id, "content", "not-a-real-category", "github", "url", OWNER_UID)


def _raw(tenant_id, pending_id):
    return pending_facts_module._collection(tenant_id).document(pending_id).get().to_dict()


def test_reject_removes_it_without_publishing_anything(tenant_id, monkeypatch):
    """Rejecting a pending fact removes it from the list and never calls publish_fact."""
    published = []
    monkeypatch.setattr(
        pending_facts_module, "publish_fact", lambda *a, **k: published.append((a, k))
    )

    pending_id = create_pending_fact(tenant_id, "content", "bug", "github", "url", OWNER_UID)
    reject_pending_fact(tenant_id, pending_id, OWNER_UID)

    assert list_pending_facts(tenant_id, OWNER_UID) == []
    assert published == []


def test_a_rejection_is_kept_with_its_time_and_without_the_text(tenant_id):
    """A rejected record keeps its status, decision time, source, and category, but drops the fact content."""
    pending_id = create_pending_fact(
        tenant_id, "Text from a PR title", "bug", "github", "https://x/1", OWNER_UID
    )

    reject_pending_fact(tenant_id, pending_id, OWNER_UID)

    kept = _raw(tenant_id, pending_id)
    assert kept["status"] == "rejected"
    assert kept["decided_at"] is not None
    assert kept["source_url"] == "https://x/1" and kept["category"] == "bug"
    assert "content" not in kept  # data minimization: the text came from other people


def test_approve_publishes_the_fact_and_removes_the_pending_copy(tenant_id, monkeypatch):
    """Approving a pending fact publishes it and leaves the pending record marked approved with its content dropped."""
    published = []
    monkeypatch.setattr(
        pending_facts_module,
        "publish_fact",
        lambda tenant_id, content, category, owner_uid, source=None: published.append(
            (tenant_id, content, category, owner_uid, source)
        ),
    )

    pending_id = create_pending_fact(
        tenant_id, "Ships with a Dockerfile", "decision", "github", "url", OWNER_UID
    )
    approve_pending_fact(tenant_id, pending_id, OWNER_UID)

    assert published == [(tenant_id, "Ships with a Dockerfile", "decision", OWNER_UID, "github")]
    assert list_pending_facts(tenant_id, OWNER_UID) == []
    kept = _raw(tenant_id, pending_id)
    assert kept["status"] == "approved" and "content" not in kept


def test_approving_a_missing_pending_fact_is_an_error(tenant_id):
    """Approving a pending fact ID that doesn't exist raises ValueError."""
    with pytest.raises(ValueError):
        approve_pending_fact(tenant_id, "does-not-exist", OWNER_UID)


def test_a_decided_fact_cannot_be_approved_again_and_rejecting_it_changes_nothing(
    tenant_id, monkeypatch
):
    """An already-approved fact can't be approved again, and rejecting it or a missing ID afterward is a no-op."""
    published = []
    monkeypatch.setattr(pending_facts_module, "publish_fact", lambda *a, **k: published.append(1))
    pending_id = create_pending_fact(tenant_id, "content", "bug", "github", "url", OWNER_UID)
    approve_pending_fact(tenant_id, pending_id, OWNER_UID)

    with pytest.raises(ValueError):
        approve_pending_fact(tenant_id, pending_id, OWNER_UID)
    reject_pending_fact(tenant_id, pending_id, OWNER_UID)  # already decided: a no-op
    reject_pending_fact(tenant_id, "does-not-exist", OWNER_UID)  # gone: also a no-op

    assert published == [1]
    assert _raw(tenant_id, pending_id)["status"] == "approved"


def test_a_pending_fact_from_before_statuses_existed_still_counts_as_pending(tenant_id):
    """A legacy record written before the status field existed still lists and counts as pending."""
    pending_facts_module._collection(tenant_id).add(
        {
            "content": "old one",
            "category": "bug",
            "source": "github",
            "source_url": "u",
            "created_at": None,
        }
    )

    assert [f["content"] for f in list_pending_facts(tenant_id, OWNER_UID)] == ["old one"]
    assert get_pending_fact_stats(tenant_id, OWNER_UID) == {
        "pending": 1,
        "approved": 0,
        "rejected": 0,
    }


def test_the_stats_count_each_status(tenant_id, monkeypatch):
    """The stats tally pending, approved, and rejected facts correctly across a mix of decisions."""
    monkeypatch.setattr(pending_facts_module, "publish_fact", lambda *a, **k: None)
    first = create_pending_fact(tenant_id, "a", "bug", "github", "u1", OWNER_UID)
    second = create_pending_fact(tenant_id, "b", "bug", "github", "u2", OWNER_UID)
    third = create_pending_fact(tenant_id, "c", "bug", "github", "u3", OWNER_UID)
    create_pending_fact(tenant_id, "d", "bug", "github", "u4", OWNER_UID)
    approve_pending_fact(tenant_id, first, OWNER_UID)
    approve_pending_fact(tenant_id, second, OWNER_UID)
    reject_pending_fact(tenant_id, third, OWNER_UID)

    assert get_pending_fact_stats(tenant_id, OWNER_UID) == {
        "pending": 1,
        "approved": 2,
        "rejected": 1,
    }


def test_stats_of_someone_elses_project_are_refused(tenant_id):
    """Requesting pending-fact stats for a tenant with an owner UID that isn't the owner raises PermissionError."""
    with pytest.raises(PermissionError):
        get_pending_fact_stats(tenant_id, "someone-else@example.com")


def test_pending_facts_are_isolated_per_tenant(tenant_id):
    """A pending fact created in one tenant does not appear in another tenant's list."""
    other_id = add_tenant(f"Other Tenant {uuid.uuid4().hex[:8]}", OWNER_UID)
    try:
        create_pending_fact(tenant_id, "content", "bug", "github", "url", OWNER_UID)
        assert list_pending_facts(other_id, OWNER_UID) == []
    finally:
        delete_tenant(other_id, OWNER_UID)


def test_deleting_a_tenant_cascades_into_its_pending_facts():
    """Deleting a tenant also removes its pending facts, so listing them afterward is refused."""
    # A dedicated tenant, not the shared fixture — this test deletes it
    # itself, and the fixture's own teardown would otherwise try (and fail)
    # to delete it again.
    own_tenant_id = add_tenant(f"Cascade Delete Test {uuid.uuid4().hex[:8]}", OWNER_UID)
    create_pending_fact(own_tenant_id, "content", "bug", "github", "url", OWNER_UID)

    delete_tenant(own_tenant_id, OWNER_UID)

    with pytest.raises(PermissionError):
        list_pending_facts(own_tenant_id, OWNER_UID)
