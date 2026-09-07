import re
from datetime import datetime, timezone

from src.firestore_client import get_client


def _slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    if not slug:
        raise ValueError(f"Could not derive a tenant_id from name '{name}'")
    return slug


def add_tenant(name: str) -> str:
    """Register a new project (tenant).

    The tenant_id is derived from the name rather than accepted as a
    parameter — a caller (human or agent) inventing an ID is exactly how
    the tenant_id mismatch in APPCE-11 happened; deriving it here removes
    the guesswork instead of relying on the caller to get it right.

    Returns:
        The generated tenant_id, e.g. "TMDB Hit Classifier" -> "tmdb_hit_classifier".
    """
    tenant_id = _slugify(name)
    client = get_client()
    client.collection("tenants").document(tenant_id).set(
        {
            "name": name,
            "status": "active",
            "created_at": datetime.now(timezone.utc),
        }
    )
    return tenant_id


def set_jira_project_key(tenant_id: str, jira_project_key: str) -> None:
    """Attach a Jira project key to an existing tenant.

    Stored on the tenant document (not a local config file) since a Jira
    project key isn't machine-specific — the deployed agent needs it too,
    unlike a local git repo path.
    """
    client = get_client()
    client.collection("tenants").document(tenant_id).update(
        {"jira_project_key": jira_project_key}
    )


def list_tenants() -> list[dict]:
    """List all known projects (tenants).

    Returns:
        A list of dicts with "tenant_id" (use this exact value when calling
        get_tenant_facts), "name" (human-readable project name), and
        "jira_project_key" (None if not set — not every tenant necessarily
        has one).
    """
    client = get_client()
    return [
        {
            "tenant_id": doc.id,
            "name": data.get("name"),
            "jira_project_key": data.get("jira_project_key"),
        }
        for doc in client.collection("tenants").stream()
        for data in [doc.to_dict()]
    ]
