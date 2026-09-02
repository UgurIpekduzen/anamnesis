from datetime import datetime, timezone

from google.cloud.firestore_v1.base_query import FieldFilter

from src.categories import validate_category
from src.firestore_client import get_client


def create_fact(tenant_id: str, content: str, category: str) -> None:
    """Write a fact to Firestore. Called by the Pub/Sub subscriber, not
    directly by callers that want the event-driven write path — use
    src.publisher.publish_fact for that instead.

    Args:
        tenant_id: The project identifier, e.g. "recruiter_ai".
        content: The fact text.
        category: One of the allowed categories (architecture, decision,
            bug, status, todo).
    """
    validate_category(category)

    client = get_client()
    now = datetime.now(timezone.utc)
    client.collection("tenants").document(tenant_id).collection("facts").add(
        {"content": content, "category": category, "created_at": now, "updated_at": now}
    )


def get_tenant_facts(tenant_id: str, category: str | None = None) -> list[dict]:
    """Retrieve stored facts for a given project (tenant).

    Args:
        tenant_id: The project identifier, e.g. "recruiter_ai".
        category: Optional filter — one of the allowed categories
            (architecture, decision, bug, status, todo). If omitted,
            all facts for the tenant are returned.

    Returns:
        A list of fact dicts with "content", "category", and "created_at".
    """
    if category is not None:
        validate_category(category)

    client = get_client()
    facts_ref = client.collection("tenants").document(tenant_id).collection("facts")

    query = (
        facts_ref
        if category is None
        else facts_ref.where(filter=FieldFilter("category", "==", category))
    )

    return [
        {
            "content": doc.get("content"),
            "category": doc.get("category"),
            "created_at": doc.get("created_at"),
        }
        for doc in query.stream()
    ]
