import uuid

import pytest

from src.facts import create_fact, delete_fact, get_fact, get_tenant_facts, update_fact
from src.firestore_client import get_client
from src.tenants import add_tenant, delete_tenant

OWNER_UID = "test-owner@example.com"


@pytest.fixture
def tenant_id():
    tenant_id = add_tenant(f"Integration Test Tenant {uuid.uuid4().hex[:8]}", OWNER_UID)
    yield tenant_id
    # Some tests delete the tenant themselves (e.g. to assert cascade
    # behavior) — tolerate that instead of failing on an already-gone
    # tenant, since get_owned_tenant now rejects it as not found.
    try:
        delete_tenant(tenant_id, OWNER_UID)
    except PermissionError:
        pass


def test_create_fact_is_retrievable_via_get_tenant_facts(tenant_id):
    create_fact(tenant_id, content="Uses React for the UI", category="architecture")

    facts = get_tenant_facts(tenant_id, OWNER_UID)
    assert len(facts) == 1
    assert facts[0]["content"] == "Uses React for the UI"
    assert facts[0]["category"] == "architecture"
    assert facts[0]["source"] == "chat"  # the default when not given (APPCE-81)


def test_create_fact_records_a_non_default_source(tenant_id):
    create_fact(tenant_id, content="From a GitHub PR", category="bug", source="github")

    assert get_tenant_facts(tenant_id, OWNER_UID)[0]["source"] == "github"


def test_a_fact_with_no_source_field_at_all_does_not_crash(tenant_id):
    # Simulates a fact written before APPCE-81 added the field (or by an
    # older deployed writer) — Firestore's doc.get() raises KeyError for a
    # field that's entirely absent, unlike dict.get, so this is worth
    # pinning down explicitly.
    get_client().collection("tenants").document(tenant_id).collection("facts").add(
        {"content": "Legacy fact", "category": "status", "created_at": None, "updated_at": None}
    )

    facts = get_tenant_facts(tenant_id, OWNER_UID)
    assert facts[0]["content"] == "Legacy fact"
    assert facts[0]["source"] is None


def test_get_tenant_facts_limit_keeps_the_newest_facts(tenant_id):
    create_fact(tenant_id, content="oldest", category="todo")
    create_fact(tenant_id, content="middle", category="todo")
    create_fact(tenant_id, content="newest", category="todo")

    limited = get_tenant_facts(tenant_id, OWNER_UID, limit=2)
    assert [f["content"] for f in limited] == ["newest", "middle"]

    # No limit still returns everything — the UI's Facts tab relies on it.
    assert len(get_tenant_facts(tenant_id, OWNER_UID)) == 3


def test_update_fact_changes_content_and_category(tenant_id):
    create_fact(tenant_id, content="Original content", category="status")
    fact_id = get_tenant_facts(tenant_id, OWNER_UID)[0]["fact_id"]

    update_fact(tenant_id, fact_id, OWNER_UID, content="Updated content", category="decision")

    facts = get_tenant_facts(tenant_id, OWNER_UID)
    assert facts[0]["content"] == "Updated content"
    assert facts[0]["category"] == "decision"


def test_delete_fact_removes_it(tenant_id):
    create_fact(tenant_id, content="Temporary fact", category="todo")
    fact_id = get_tenant_facts(tenant_id, OWNER_UID)[0]["fact_id"]

    delete_fact(tenant_id, fact_id, OWNER_UID)

    assert get_tenant_facts(tenant_id, OWNER_UID) == []


def test_get_fact_returns_one_fact(tenant_id):
    create_fact(tenant_id, content="Uses PostgreSQL", category="architecture")
    fact_id = get_tenant_facts(tenant_id, OWNER_UID)[0]["fact_id"]

    fact = get_fact(tenant_id, fact_id, OWNER_UID)

    assert (fact["fact_id"], fact["content"], fact["category"]) == (fact_id, "Uses PostgreSQL", "architecture")


def test_get_fact_raises_lookup_error_for_a_missing_fact_and_permission_error_for_a_non_owner(tenant_id):
    create_fact(tenant_id, content="x", category="bug")
    fact_id = get_tenant_facts(tenant_id, OWNER_UID)[0]["fact_id"]

    with pytest.raises(LookupError):
        get_fact(tenant_id, "no-such-fact", OWNER_UID)
    with pytest.raises(PermissionError):
        get_fact(tenant_id, fact_id, "someone-else@example.com")


def test_get_tenant_facts_rejects_a_non_owner(tenant_id):
    create_fact(tenant_id, content="Only the owner should see this", category="bug")

    with pytest.raises(PermissionError):
        get_tenant_facts(tenant_id, "someone-else@example.com")


def test_delete_tenant_cascade_deletes_its_facts(tenant_id):
    create_fact(tenant_id, content="Should be cascade-deleted", category="bug")

    delete_tenant(tenant_id, OWNER_UID)

    # The tenant document is gone at this point, so get_tenant_facts would
    # now correctly reject the call (see get_owned_tenant) — read the
    # facts subcollection directly to confirm the cascade delete instead.
    client = get_client()
    remaining = list(
        client.collection("tenants").document(tenant_id).collection("facts").stream()
    )
    assert remaining == []
