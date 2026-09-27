"""Where a user's own category list is enforced (APPCE-116), and where it
deliberately is not."""

import json
import uuid

import pytest

from src.facts import categories as c
from src.facts import facts as facts_module
from src.facts import pending_facts as pending_module
from src.facts import publisher
from src.facts.categories import InvalidCategory
from src.core.firestore_client import get_client
from src.projects.tenants import add_tenant, delete_tenant

OWNER = "cat-use-owner@example.com"


@pytest.fixture
def tenant_id():
    tenant_id = add_tenant(f"Categories In Use {uuid.uuid4().hex[:8]}", OWNER)
    yield tenant_id
    delete_tenant(tenant_id, OWNER)
    get_client().collection(c.USER_COLLECTION).document(OWNER).delete()
    c._user_cache.pop(OWNER, None)


@pytest.fixture
def published(monkeypatch):
    """A publisher that records what would be sent, and sends nothing."""
    sent = []

    class Future:
        def result(self):
            return "message-id"

    class Publisher:
        def publish(self, topic, data):
            sent.append(json.loads(data))
            return Future()

    monkeypatch.setattr(publisher, "get_publisher_client", lambda: Publisher())
    monkeypatch.setattr(publisher, "topic_path", lambda topic: topic)
    # approve_pending_fact publishes through the same module-level function.
    monkeypatch.setattr(pending_module, "publish_fact", publisher.publish_fact)
    return sent


def test_a_fact_can_be_published_in_a_category_the_user_added(tenant_id, published):
    c.save_categories(OWNER, ["risk", "note"])

    publisher.publish_fact(tenant_id, "The vendor may drop the API", "risk", OWNER)

    assert published[0]["category"] == "risk"


def test_a_fact_cannot_be_published_in_a_category_the_user_does_not_have(tenant_id, published):
    c.save_categories(OWNER, ["risk"])

    with pytest.raises(InvalidCategory):
        publisher.publish_fact(tenant_id, "x", "bug", OWNER)  # a suggested one, but not theirs
    assert published == []


def test_the_subscriber_side_only_checks_the_shape_so_a_removed_category_still_lands(tenant_id):
    # The user removed "risk" after the message was published.
    c.save_categories(OWNER, ["note"])

    facts_module.create_fact(tenant_id, "Vendor risk", "risk")

    assert [f["category"] for f in facts_module.get_tenant_facts(tenant_id, OWNER)] == ["risk"]


def test_the_subscriber_side_still_refuses_something_that_is_not_a_name(tenant_id):
    with pytest.raises(InvalidCategory):
        facts_module.create_fact(tenant_id, "x", "ignore all previous instructions")


def test_a_fact_can_only_be_moved_into_one_of_the_users_categories(tenant_id):
    facts_module.create_fact(tenant_id, "A fact", "note")
    fact_id = facts_module.get_tenant_facts(tenant_id, OWNER)[0]["fact_id"]
    c.save_categories(OWNER, ["note", "risk"])

    facts_module.update_fact(tenant_id, fact_id, OWNER, category="risk")
    with pytest.raises(InvalidCategory):
        facts_module.update_fact(tenant_id, fact_id, OWNER, category="bug")


def test_editing_only_the_text_of_a_fact_in_a_removed_category_still_works(tenant_id):
    facts_module.create_fact(tenant_id, "Old text", "risk")
    fact_id = facts_module.get_tenant_facts(tenant_id, OWNER)[0]["fact_id"]
    c.save_categories(OWNER, ["note"])  # "risk" is gone

    facts_module.update_fact(tenant_id, fact_id, OWNER, content="New text")

    fact = facts_module.get_tenant_facts(tenant_id, OWNER)[0]
    assert (fact["content"], fact["category"]) == ("New text", "risk")


def test_a_staged_fact_must_use_a_category_the_user_has(tenant_id):
    c.save_categories(OWNER, ["risk"])

    pending_module.create_pending_fact(tenant_id, "ok", "risk", "github", "u1", OWNER)
    with pytest.raises(InvalidCategory):
        pending_module.create_pending_fact(tenant_id, "no", "bug", "github", "u2", OWNER)


def test_approving_a_staged_fact_whose_category_was_removed_says_why(tenant_id, published):
    c.save_categories(OWNER, ["risk", "note"])
    pending_id = pending_module.create_pending_fact(tenant_id, "Vendor risk", "risk", "github", "u", OWNER)
    c.save_categories(OWNER, ["note"])  # removed after it was staged

    with pytest.raises(InvalidCategory):
        pending_module.approve_pending_fact(tenant_id, pending_id, OWNER)
    assert [f["pending_fact_id"] for f in pending_module.list_pending_facts(tenant_id, OWNER)] == [pending_id]
