import re
from datetime import datetime, timezone

from google.cloud import firestore

from src.firestore_client import get_client


def _slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    if not slug:
        raise ValueError(f"Could not derive a tenant_id from name '{name}'")
    return slug


def get_owned_tenant(tenant_id: str, owner_uid: str) -> dict:
    """Fetch a tenant document, enforcing that it belongs to owner_uid.

    Raises:
        PermissionError: if the tenant doesn't exist or belongs to a
            different owner — callers must not distinguish between the
            two, so a user can't tell "wrong owner" from "never existed"
            for someone else's project (see APPCE-48).
    """
    client = get_client()
    doc = client.collection("tenants").document(tenant_id).get()
    if not doc.exists or doc.to_dict().get("owner_uid") != owner_uid:
        raise PermissionError(f"No project '{tenant_id}' found for this user.")
    return doc.to_dict()


def add_tenant(name: str, owner_uid: str) -> str:
    """Register a new project (tenant), owned by owner_uid.

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
            "owner_uid": owner_uid,
            "created_at": datetime.now(timezone.utc),
        }
    )
    return tenant_id


def rename_tenant(tenant_id: str, new_name: str, owner_uid: str) -> None:
    """Change a tenant's display name.

    The tenant_id itself (the Firestore document ID) is immutable — it
    stays derived from whatever name was used at add_tenant time.
    """
    get_owned_tenant(tenant_id, owner_uid)
    client = get_client()
    client.collection("tenants").document(tenant_id).update({"name": new_name})


def delete_tenant(tenant_id: str, owner_uid: str) -> None:
    """Delete a tenant and all of its facts.

    Cascade-deletes the "facts" subcollection first — leaving orphaned
    facts behind a deleted tenant would work against this project's data
    minimization principle (see APPCE-29) for no benefit, since nothing
    can reference them once the tenant document is gone.
    """
    get_owned_tenant(tenant_id, owner_uid)
    client = get_client()
    tenant_ref = client.collection("tenants").document(tenant_id)

    for fact_doc in tenant_ref.collection("facts").stream():
        fact_doc.reference.delete()

    tenant_ref.delete()


def set_jira_project_key(tenant_id: str, jira_project_key: str, owner_uid: str) -> None:
    """Attach a Jira project key to an existing tenant."""
    get_owned_tenant(tenant_id, owner_uid)
    client = get_client()
    client.collection("tenants").document(tenant_id).update(
        {"jira_project_key": jira_project_key}
    )


def set_git_repo_path(tenant_id: str, git_repo_path: str, owner_uid: str) -> None:
    """Attach a local git repo path to an existing tenant, used by
    git_activity_sync.py to summarize recent commit activity (see
    APPCE-28, APPCE-34).

    This is machine-specific (see APPCE-34): storing it on the tenant
    document means it only makes sense on the machine whose filesystem
    it refers to — if you sync this project across multiple machines,
    set it separately on each, or leave it unset where the repo doesn't
    exist locally.
    """
    get_owned_tenant(tenant_id, owner_uid)
    client = get_client()
    client.collection("tenants").document(tenant_id).update(
        {"git_repo_path": git_repo_path}
    )


def list_tenants(owner_uid: str) -> list[dict]:
    """List all projects (tenants) owned by owner_uid.

    Returns:
        A list of dicts with "tenant_id" (use this exact value when calling
        get_tenant_facts), "name" (human-readable project name),
        "jira_project_key" (None if not set), and "git_repo_path" (None if
        not set — not every tenant necessarily has either).
    """
    client = get_client()
    query = client.collection("tenants").where(
        filter=firestore.FieldFilter("owner_uid", "==", owner_uid)
    )
    return [
        {
            "tenant_id": doc.id,
            "name": data.get("name"),
            "jira_project_key": data.get("jira_project_key"),
            "git_repo_path": data.get("git_repo_path"),
        }
        for doc in query.stream()
        for data in [doc.to_dict()]
    ]
