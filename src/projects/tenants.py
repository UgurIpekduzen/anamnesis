import re
from datetime import datetime, timezone

from google.api_core.exceptions import AlreadyExists
from google.cloud import firestore

from src.core.firestore_client import get_client
from src.projects.validation import validate_github_repo, validate_project_key


# Named here (not in src/projects/chat_history.py) so delete_tenant can cascade into
# it without a circular import — chat_history depends on this module.
CHAT_TURNS_COLLECTION = "chat_turns"

# Same reasoning as CHAT_TURNS_COLLECTION above — named here so
# delete_tenant can cascade into it without src/facts/pending_facts.py and
# src/projects/tenants.py importing each other.
PENDING_FACTS_COLLECTION = "pending_facts"


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
            for someone else's project.
    """
    client = get_client()
    doc = client.collection("tenants").document(tenant_id).get()
    if not doc.exists or doc.to_dict().get("owner_uid") != owner_uid:
        raise PermissionError(f"No project '{tenant_id}' found for this user.")
    return doc.to_dict()


class TenantNameTaken(ValueError):
    """The project id derived from a name is already in use. The id is shared
    by every user, so this can't say whose project it is."""


def add_tenant(name: str, owner_uid: str) -> str:
    """Register a new project (tenant), owned by owner_uid.

    The tenant_id is derived from the name rather than accepted as a
    parameter — a caller (human or agent) inventing an ID is exactly how
    the tenant_id mismatch that happened before; deriving it here removes
    the guesswork instead of relying on the caller to get it right.

    Returns:
        The generated tenant_id, e.g. "My Project" -> "my_project".

    Raises:
        TenantNameTaken: a project with this id exists already — whoever's it
            is. The document is created, never written over: the id is one
            namespace for all users, and a write over it would hand the
            existing project (and everything under it) to the caller.
    """
    tenant_id = _slugify(name)
    client = get_client()
    try:
        client.collection("tenants").document(tenant_id).create(
            {
                "name": name,
                "status": "active",
                "owner_uid": owner_uid,
                "created_at": datetime.now(timezone.utc),
            }
        )
    except AlreadyExists as exc:
        raise TenantNameTaken("That project name isn't available.") from exc
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
    """Delete a tenant and everything stored under it.

    Cascade-deletes the "facts" and saved chat-turn subcollections first —
    leaving orphans behind a deleted tenant would work against this
    project's data minimization principle for no benefit,
    since nothing can reference them once the tenant document is gone.
    """
    get_owned_tenant(tenant_id, owner_uid)
    client = get_client()
    tenant_ref = client.collection("tenants").document(tenant_id)

    for subcollection in ("facts", CHAT_TURNS_COLLECTION, PENDING_FACTS_COLLECTION):
        for doc in tenant_ref.collection(subcollection).stream():
            doc.reference.delete()

    tenant_ref.delete()


def set_jira_project_key(tenant_id: str, jira_project_key: str, owner_uid: str) -> None:
    """Attach a Jira project key to an existing tenant.

    Raises:
        ValueError: jira_project_key isn't a plain project key such as "APPCE".
    """
    validate_project_key(jira_project_key)
    get_owned_tenant(tenant_id, owner_uid)
    client = get_client()
    client.collection("tenants").document(tenant_id).update(
        {"jira_project_key": jira_project_key}
    )


def clear_jira_project_key(tenant_id: str, owner_uid: str) -> None:
    """Detach the Jira project key from a tenant."""
    get_owned_tenant(tenant_id, owner_uid)
    client = get_client()
    client.collection("tenants").document(tenant_id).update({"jira_project_key": firestore.DELETE_FIELD})


def set_github_repo(tenant_id: str, github_repo: str, owner_uid: str) -> None:
    """Attach a GitHub repo (owner/name) to an existing tenant, used to poll
    its PRs/issues for facts.

    Raises:
        ValueError: github_repo isn't a plain "owner/name" string.
    """
    validate_github_repo(github_repo)
    tenant = get_owned_tenant(tenant_id, owner_uid)
    changes = {"github_repo": github_repo}
    if tenant.get("github_repo") != github_repo:
        # Polling skips whatever was last updated before the previous poll.
        # That cut-off belongs to the old repo; keeping it would make the new
        # repo's existing PRs and issues look "already processed".
        changes["github_polled_at"] = firestore.DELETE_FIELD
    client = get_client()
    client.collection("tenants").document(tenant_id).update(changes)


def clear_github_repo(tenant_id: str, owner_uid: str) -> None:
    """Detach the GitHub repo from a tenant, which stops it being polled.

    The poll cut-off goes with it, for the reason given in set_github_repo.
    """
    get_owned_tenant(tenant_id, owner_uid)
    client = get_client()
    client.collection("tenants").document(tenant_id).update(
        {"github_repo": firestore.DELETE_FIELD, "github_polled_at": firestore.DELETE_FIELD}
    )


def mark_github_polled(tenant_id: str, owner_uid: str) -> None:
    """Record that this tenant's GitHub repo was just polled.

    Read back via get_owned_tenant (not list_tenants — this is internal
    bookkeeping, not something worth surfacing to the chat agent or UI).
    Lets a repeated poll skip PRs/issues it already processed, instead of
    re-extracting and re-staging the same pending facts every run.

    Also clears any github_poll_failed_at/github_poll_failure_kind left by a
    previous failed run — a poll only reaches this call once it
    has succeeded, so a prior failure no longer applies.
    """
    get_owned_tenant(tenant_id, owner_uid)
    client = get_client()
    client.collection("tenants").document(tenant_id).update(
        {
            "github_polled_at": datetime.now(timezone.utc),
            "github_poll_failed_at": firestore.DELETE_FIELD,
            "github_poll_failure_kind": firestore.DELETE_FIELD,
        }
    )


def mark_github_poll_failed(tenant_id: str, kind: str) -> None:
    """Record that this tenant's GitHub poll just failed.

    No owner_uid check, unlike every other tenant write here — called only
    from the GitHub polling job (src.integrations.github.polling), which
    runs system-wide across every owner (see list_tenants_with_github_repo),
    the same trust boundary that function already documents.

    kind is a coarse classification ("auth", "not_found", "other"), never
    the raw exception text — this is surfaced in the Admin panel, and the
    raw error could echo a token or other credential.
    """
    client = get_client()
    client.collection("tenants").document(tenant_id).update(
        {
            "github_poll_failed_at": datetime.now(timezone.utc),
            "github_poll_failure_kind": kind,
        }
    )


def list_broken_github_connections() -> list[dict]:
    """Every tenant (across all owners) whose last GitHub poll failed
    (see mark_github_poll_failed).

    Used only by the Admin panel's owner-only "broken connections" view —
    the same trust boundary as list_tenants_with_github_repo, and for the
    same reason: this necessarily spans every owner, not just one.

    Returns:
        A list of dicts with "owner_uid", "tenant_id", "name",
        "kind" (the classification from mark_github_poll_failed) and
        "failed_at". A tenant that has never failed, or that has since
        polled successfully (mark_github_polled clears these fields), is
        absent.
    """
    client = get_client()
    query = client.collection("tenants").where(
        filter=firestore.FieldFilter("github_poll_failed_at", "!=", None)
    )
    return [
        {
            "owner_uid": data.get("owner_uid"),
            "tenant_id": doc.id,
            "name": data.get("name"),
            "kind": data.get("github_poll_failure_kind"),
            "failed_at": data.get("github_poll_failed_at"),
        }
        for doc in query.stream()
        for data in [doc.to_dict()]
    ]


def list_tenants_with_github_repo() -> list[dict]:
    """Every tenant (across all owners) with a linked GitHub repo.

    Used only by the GitHub polling job (src.integrations.github.polling), which needs
    to poll every linked repo system-wide, not one owner's tenants — the
    only caller that legitimately needs to see across owner_uid at all,
    since it runs as a trusted, non-user-triggered job.

    Returns:
        A list of dicts with "owner_uid" and "tenant_id" only, enough to
        call poll_tenant_github_activity for each.
    """
    client = get_client()
    query = client.collection("tenants").where(
        filter=firestore.FieldFilter("github_repo", "!=", None)
    )
    return [
        {"owner_uid": doc.get("owner_uid"), "tenant_id": doc.id}
        for doc in query.stream()
    ]


def list_tenants(owner_uid: str) -> list[dict]:
    """List all projects (tenants) owned by owner_uid.

    Returns:
        A list of dicts with "tenant_id" (use this exact value when calling
        get_tenant_facts), "name" (human-readable project name),
        "jira_project_key" (None if not set) and "github_repo" (None if
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
            "github_repo": data.get("github_repo"),
        }
        for doc in query.stream()
        for data in [doc.to_dict()]
    ]
