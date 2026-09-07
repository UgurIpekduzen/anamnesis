from datetime import datetime, timezone

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


def get_tenant_facts(tenant_id: str) -> list[dict]:
    """Retrieve all stored facts for a given project (tenant).

    No category filter is exposed here on purpose (see APPCE-26): the
    agent reliably ignored instructions not to infer a category from
    general wording, so the ability to filter was removed instead of
    relying on a prompt constraint. Each returned fact still carries its
    category — the caller filters or summarizes in its own response if
    needed.

    Args:
        tenant_id: The project identifier, e.g. "recruiter_ai".

    Returns:
        A list of fact dicts with "content", "category", and "created_at".
    """
    client = get_client()
    facts_ref = client.collection("tenants").document(tenant_id).collection("facts")

    return [
        {
            "content": doc.get("content"),
            "category": doc.get("category"),
            "created_at": doc.get("created_at"),
        }
        for doc in facts_ref.stream()
    ]
