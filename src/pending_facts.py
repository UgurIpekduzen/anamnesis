from datetime import datetime, timezone

from src.categories import validate_category
from src.firestore_client import get_client
from src.publisher import publish_fact
from src.tenants import PENDING_FACTS_COLLECTION, get_owned_tenant


def _collection(tenant_id: str):
    return get_client().collection("tenants").document(tenant_id).collection(PENDING_FACTS_COLLECTION)


def create_pending_fact(
    tenant_id: str, content: str, category: str, source: str, source_url: str, owner_uid: str
) -> str:
    """Stage a fact for review instead of publishing it — used for facts
    the agent didn't extract from the user's own chat messages (currently
    just GitHub, see APPCE-81), which a person never actually asked to be
    remembered and hasn't seen yet.

    Args:
        source: Where this candidate fact came from, e.g. "github".
        source_url: A link back to the origin (e.g. the PR/issue), shown
            to the user so they can judge the fact in context before
            approving it.

    Returns:
        The generated pending_fact_id.
    """
    get_owned_tenant(tenant_id, owner_uid)
    validate_category(category)

    now = datetime.now(timezone.utc)
    _, doc_ref = _collection(tenant_id).add(
        {
            "content": content,
            "category": category,
            "source": source,
            "source_url": source_url,
            "created_at": now,
        }
    )
    return doc_ref.id


def list_pending_facts(tenant_id: str, owner_uid: str) -> list[dict]:
    """All facts awaiting approval for a project, oldest first."""
    get_owned_tenant(tenant_id, owner_uid)
    return [
        {
            "pending_fact_id": doc.id,
            "content": doc.get("content"),
            "category": doc.get("category"),
            "source": doc.get("source"),
            "source_url": doc.get("source_url"),
            "created_at": doc.get("created_at"),
        }
        for doc in _collection(tenant_id).order_by("created_at").stream()
    ]


def approve_pending_fact(tenant_id: str, pending_fact_id: str, owner_uid: str) -> None:
    """Turn a pending fact into a real one via the normal publish path
    (src.publisher.publish_fact), then remove the staged copy.
    """
    get_owned_tenant(tenant_id, owner_uid)
    doc_ref = _collection(tenant_id).document(pending_fact_id)
    doc = doc_ref.get()
    if not doc.exists:
        raise ValueError(f"No pending fact '{pending_fact_id}' for tenant '{tenant_id}'.")

    data = doc.to_dict()
    publish_fact(tenant_id, data["content"], data["category"], owner_uid, source=data.get("source", "chat"))
    doc_ref.delete()


def reject_pending_fact(tenant_id: str, pending_fact_id: str, owner_uid: str) -> None:
    """Discard a pending fact without ever publishing it."""
    get_owned_tenant(tenant_id, owner_uid)
    _collection(tenant_id).document(pending_fact_id).delete()
