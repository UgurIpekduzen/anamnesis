from google.cloud.firestore_v1.base_query import FieldFilter

from src.categories import validate_category
from src.firestore_client import get_client


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
