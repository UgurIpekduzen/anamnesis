from datetime import datetime, timezone

from google.cloud import firestore

from src.categories import validate_category
from src.firestore_client import get_client
from src.tenants import get_owned_tenant


def create_fact(tenant_id: str, content: str, category: str, source: str = "chat") -> None:
    """Write a fact to Firestore. Called by the Pub/Sub subscriber, not
    directly by callers that want the event-driven write path — use
    src.publisher.publish_fact for that instead.

    Args:
        tenant_id: The project identifier, e.g. "recruiter_ai".
        content: The fact text.
        category: One of the allowed categories (architecture, decision,
            bug, status, todo).
        source: Where this fact came from — "chat" (the agent, during a
            conversation) or "github" (approved from the Pending review
            queue, see APPCE-81/82).
    """
    validate_category(category)

    client = get_client()
    now = datetime.now(timezone.utc)
    client.collection("tenants").document(tenant_id).collection("facts").add(
        {"content": content, "category": category, "source": source, "created_at": now, "updated_at": now}
    )


def get_tenant_facts(tenant_id: str, owner_uid: str, limit: int | None = None) -> list[dict]:
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
        A list of fact dicts with "fact_id" (use this exact value when
        calling update_fact/delete_fact), "content", "category", "source"
        ("chat" or "github" — absent on facts written before APPCE-81
        added it, in which case this is None), and "created_at".
    """
    get_owned_tenant(tenant_id, owner_uid)
    client = get_client()
    facts_ref = client.collection("tenants").document(tenant_id).collection("facts")

    # limit is for the agent's tool (a fact list lands in the model's
    # context and stays there — see APPCE-59); the UI's Facts tab passes
    # none and still gets everything. Newest first so a cap keeps the
    # most relevant facts.
    query = facts_ref
    if limit is not None:
        query = facts_ref.order_by("created_at", direction=firestore.Query.DESCENDING).limit(limit)

    return [
        {
            "fact_id": doc.id,
            "content": doc.get("content"),
            "category": doc.get("category"),
            "source": doc.get("source"),
            "created_at": doc.get("created_at"),
        }
        for doc in query.stream()
    ]


def update_fact(
    tenant_id: str,
    fact_id: str,
    owner_uid: str,
    content: str | None = None,
    category: str | None = None,
) -> None:
    """Update an existing fact's content and/or category.

    At least one of content/category should be given — omit the field
    you don't want to change instead of passing its old value back in.
    """
    get_owned_tenant(tenant_id, owner_uid)
    if category is not None:
        validate_category(category)

    updates = {"updated_at": datetime.now(timezone.utc)}
    if content is not None:
        updates["content"] = content
    if category is not None:
        updates["category"] = category

    client = get_client()
    client.collection("tenants").document(tenant_id).collection("facts").document(
        fact_id
    ).update(updates)


def delete_fact(tenant_id: str, fact_id: str, owner_uid: str) -> None:
    """Delete a single fact."""
    get_owned_tenant(tenant_id, owner_uid)
    client = get_client()
    client.collection("tenants").document(tenant_id).collection("facts").document(
        fact_id
    ).delete()
