import json

from src.facts.categories import validate_category_for
from src.core.pubsub_client import get_publisher_client, topic_path
from src.projects.tenants import get_owned_tenant

TOPIC_ID = "fact-events"


def publish_fact(tenant_id: str, content: str, category: str, owner_uid: str, source: str = "chat") -> str:
    """Publish a fact-creation event instead of writing to Firestore directly.

    A subscriber (src/subscriber.py) picks up the message and performs the
    actual Firestore write, decoupling the caller from Firestore's
    availability. Ownership is checked here, before the message is
    published — the subscriber trusts tenant_id once a message reaches
    it, since only this function can have put it there.

    Args:
        tenant_id: The project identifier, e.g. "my_project".
        content: The fact text.
        category: One of the owner's categories (see src.facts.categories).
        source: Where this fact came from — "chat" or "github" (see
            src.facts.facts.create_fact).

    Returns:
        The published message ID.
    """
    get_owned_tenant(tenant_id, owner_uid)
    validate_category_for(owner_uid, category)

    payload = {"tenant_id": tenant_id, "content": content, "category": category, "source": source}
    data = json.dumps(payload).encode("utf-8")

    publisher = get_publisher_client()
    future = publisher.publish(topic_path(TOPIC_ID), data=data)
    return future.result()
