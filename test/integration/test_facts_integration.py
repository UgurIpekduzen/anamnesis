import uuid

import pytest

from src.facts import create_fact, delete_fact, get_tenant_facts, update_fact
from src.tenants import add_tenant, delete_tenant


@pytest.fixture
def tenant_id():
    tenant_id = add_tenant(f"Integration Test Tenant {uuid.uuid4().hex[:8]}")
    yield tenant_id
    delete_tenant(tenant_id)


def test_create_fact_is_retrievable_via_get_tenant_facts(tenant_id):
    create_fact(tenant_id, content="Uses Streamlit for the UI", category="architecture")

    facts = get_tenant_facts(tenant_id)
    assert len(facts) == 1
    assert facts[0]["content"] == "Uses Streamlit for the UI"
    assert facts[0]["category"] == "architecture"


def test_update_fact_changes_content_and_category(tenant_id):
    create_fact(tenant_id, content="Original content", category="status")
    fact_id = get_tenant_facts(tenant_id)[0]["fact_id"]

    update_fact(tenant_id, fact_id, content="Updated content", category="decision")

    facts = get_tenant_facts(tenant_id)
    assert facts[0]["content"] == "Updated content"
    assert facts[0]["category"] == "decision"


def test_delete_fact_removes_it(tenant_id):
    create_fact(tenant_id, content="Temporary fact", category="todo")
    fact_id = get_tenant_facts(tenant_id)[0]["fact_id"]

    delete_fact(tenant_id, fact_id)

    assert get_tenant_facts(tenant_id) == []


def test_delete_tenant_cascade_deletes_its_facts(tenant_id):
    create_fact(tenant_id, content="Should be cascade-deleted", category="bug")

    delete_tenant(tenant_id)

    # Re-adding under a fresh call would create a new tenant_id from the
    # same name, so read the (now-deleted) tenant's facts subcollection
    # directly instead of relying on add_tenant/delete_tenant symmetry.
    assert get_tenant_facts(tenant_id) == []
