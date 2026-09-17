import json

from src.categories import validate_category
from src.pubsub_client import get_publisher_client, topic_path
from src.tenants import get_owned_tenant

TOPIC_ID = "fact-events"


def publish_fact(tenant_id: str, content: str, category: str, owner_uid: str) -> str:
    """Publish a fact-creation event instead of writing to Firestore directly.

    A subscriber (src/subscriber.py) picks up the message and performs the
    actual Firestore write, decoupling the caller from Firestore's
    availability. Ownership is checked here, before the message is
    published — the subscriber trusts tenant_id once a message reaches
    it, since only this function can have put it there (see APPCE-48).

    Args:
        tenant_id: The project identifier, e.g. "recruiter_ai".
        content: The fact text.
        category: One of the allowed categories (architecture, decision,
            bug, status, todo).

    Returns:
        The published message ID.
    """
    get_owned_tenant(tenant_id, owner_uid)
    validate_category(category)

    payload = {"tenant_id": tenant_id, "content": content, "category": category}
    data = json.dumps(payload).encode("utf-8")

    publisher = get_publisher_client()
    future = publisher.publish(topic_path(TOPIC_ID), data=data)
    return future.result()
