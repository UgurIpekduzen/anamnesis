import uuid

import pytest

from src import pending_facts as pending_facts_module
from src.pending_facts import (
    approve_pending_fact,
    create_pending_fact,
    list_pending_facts,
    reject_pending_fact,
)
from src.tenants import add_tenant, delete_tenant

OWNER_UID = "test-owner@example.com"


@pytest.fixture
def tenant_id():
    tenant_id = add_tenant(f"Pending Facts Test {uuid.uuid4().hex[:8]}", OWNER_UID)
    yield tenant_id
    delete_tenant(tenant_id, OWNER_UID)


def test_a_created_pending_fact_is_listed(tenant_id):
    pending_id = create_pending_fact(
        tenant_id, "Uses Postgres for the primary store", "architecture", "github", "https://github.com/o/r/pull/1", OWNER_UID
    )

    listed = list_pending_facts(tenant_id, OWNER_UID)

    assert len(listed) == 1
    assert listed[0]["pending_fact_id"] == pending_id
    assert listed[0]["content"] == "Uses Postgres for the primary store"
    assert listed[0]["category"] == "architecture"
    assert listed[0]["source"] == "github"
    assert listed[0]["source_url"] == "https://github.com/o/r/pull/1"


def test_create_pending_fact_rejects_an_invalid_category(tenant_id):
    with pytest.raises(ValueError):
        create_pending_fact(tenant_id, "content", "not-a-real-category", "github", "url", OWNER_UID)


def test_reject_removes_it_without_publishing_anything(tenant_id, monkeypatch):
    published = []
    monkeypatch.setattr(pending_facts_module, "publish_fact", lambda *a, **k: published.append((a, k)))

    pending_id = create_pending_fact(tenant_id, "content", "bug", "github", "url", OWNER_UID)
    reject_pending_fact(tenant_id, pending_id, OWNER_UID)

    assert list_pending_facts(tenant_id, OWNER_UID) == []
    assert published == []


def test_approve_publishes_the_fact_and_removes_the_pending_copy(tenant_id, monkeypatch):
    published = []
    monkeypatch.setattr(
        pending_facts_module,
        "publish_fact",
        lambda tenant_id, content, category, owner_uid, source=None: published.append(
            (tenant_id, content, category, owner_uid, source)
        ),
    )

    pending_id = create_pending_fact(tenant_id, "Ships with a Dockerfile", "decision", "github", "url", OWNER_UID)
    approve_pending_fact(tenant_id, pending_id, OWNER_UID)

    assert published == [(tenant_id, "Ships with a Dockerfile", "decision", OWNER_UID, "github")]
    assert list_pending_facts(tenant_id, OWNER_UID) == []


def test_approving_a_missing_pending_fact_is_an_error(tenant_id):
    with pytest.raises(ValueError):
        approve_pending_fact(tenant_id, "does-not-exist", OWNER_UID)


def test_pending_facts_are_isolated_per_tenant(tenant_id):
    other_id = add_tenant(f"Other Tenant {uuid.uuid4().hex[:8]}", OWNER_UID)
    try:
        create_pending_fact(tenant_id, "content", "bug", "github", "url", OWNER_UID)
        assert list_pending_facts(other_id, OWNER_UID) == []
    finally:
        delete_tenant(other_id, OWNER_UID)


def test_deleting_a_tenant_cascades_into_its_pending_facts():
    # A dedicated tenant, not the shared fixture — this test deletes it
    # itself, and the fixture's own teardown would otherwise try (and fail)
    # to delete it again.
    own_tenant_id = add_tenant(f"Cascade Delete Test {uuid.uuid4().hex[:8]}", OWNER_UID)
    create_pending_fact(own_tenant_id, "content", "bug", "github", "url", OWNER_UID)

    delete_tenant(own_tenant_id, OWNER_UID)

    with pytest.raises(PermissionError):
        list_pending_facts(own_tenant_id, OWNER_UID)
