from src.firestore_client import get_client


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
