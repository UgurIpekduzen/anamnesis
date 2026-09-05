from datetime import datetime, timezone

from src.firestore_client import get_client


def add_tenant(tenant_id: str, name: str) -> None:
    """Register a new project (tenant). Called once per project by hand —
    Cloud Run has no access to local repos to discover projects on its own.
    """
    client = get_client()
    client.collection("tenants").document(tenant_id).set(
        {
            "name": name,
            "status": "active",
            "created_at": datetime.now(timezone.utc),
        }
    )


def list_tenants() -> list[dict]:
    """List all known projects (tenants).

    Returns:
        A list of dicts with "tenant_id" (use this exact value when calling
        get_tenant_facts) and "name" (human-readable project name).
    """
    client = get_client()
    return [
        {"tenant_id": doc.id, "name": doc.get("name")}
        for doc in client.collection("tenants").stream()
    ]
