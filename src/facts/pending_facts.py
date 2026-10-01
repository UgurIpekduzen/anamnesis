"""Staging area for facts a person hasn't seen or approved yet (currently
just GitHub-derived ones), reviewed in the Pending tab before they become
real facts via src.facts.publisher.publish_fact."""

from datetime import datetime, timezone

from google.cloud import firestore

from src.facts.categories import validate_category_for
from src.facts.facts import get_tenant_facts
from src.core.firestore_client import get_client
from src.facts.publisher import publish_fact
from src.facts.similar_facts import find_similar_facts
from src.projects.tenants import PENDING_FACTS_COLLECTION, get_owned_tenant

# A pending fact is never deleted once it is decided: the document
# stays with a status, so the approval rate can be counted and a source that
# was already approved or rejected is not proposed again. Documents from
# before this field existed have no status and count as pending.
PENDING = "pending"
APPROVED = "approved"
REJECTED = "rejected"

# What get_pending_facts_summary returns stays in the model's context for
# later turns, so it is kept small like the other read tools.
MAX_PENDING_FOR_REVIEW = 20
MAX_PENDING_CONTENT_CHARS = 200


def _collection(tenant_id: str):
    return (
        get_client().collection("tenants").document(tenant_id).collection(PENDING_FACTS_COLLECTION)
    )


def create_pending_fact(
    tenant_id: str, content: str, category: str, source: str, source_url: str, owner_uid: str
) -> str:
    """Stage a fact for review instead of publishing it — used for facts
    the agent didn't extract from the user's own chat messages (currently
    just GitHub), which a person never actually asked to be
    remembered and hasn't seen yet.

    Args:
        source (str): Where this candidate fact came from, e.g. "github".
        source_url (str): A link back to the origin (e.g. the PR/issue),
            shown to the user so they can judge the fact in context before
            approving it.

    Returns:
        The generated pending_fact_id.
    """
    get_owned_tenant(tenant_id, owner_uid)
    validate_category_for(owner_uid, category)

    now = datetime.now(timezone.utc)
    _, doc_ref = _collection(tenant_id).add(
        {
            "content": content,
            "category": category,
            "source": source,
            "source_url": source_url,
            "status": PENDING,
            "created_at": now,
        }
    )
    return doc_ref.id


def has_pending_fact_for_source(tenant_id: str, source_url: str) -> bool:
    """Whether a fact from this origin (e.g. a PR/issue URL) was already
    staged: still waiting for review, or approved or rejected before.

    Lets the GitHub poller stay idempotent: Cloud Scheduler is
    at-least-once, so a retried or overlapping run must not stage the same
    item twice — and checking before the LLM extraction also skips its cost.
    No ownership check: callers are trusted server-side code that already
    resolved the tenant.

    Args:
        tenant_id (str): The project identifier, e.g. "my_project".
        source_url (str): The origin URL to check for an existing staged
            fact (e.g. the PR/issue link).
    """
    query = (
        _collection(tenant_id)
        .where(filter=firestore.FieldFilter("source_url", "==", source_url))
        .limit(1)
    )
    return any(True for _ in query.stream())


def _is_pending(data: dict) -> bool:
    return data.get("status", PENDING) == PENDING


def list_pending_facts(tenant_id: str, owner_uid: str) -> list[dict]:
    """All facts awaiting approval for a project, oldest first.

    Args:
        tenant_id (str): The project identifier, e.g. "my_project".
    """
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
        if _is_pending(doc.to_dict())
    ]


def _decide(doc_ref, status: str) -> None:
    """Record a decision. The fact's text goes: the rate and the "already
    seen" check only need the source, and the text was derived from what
    other people wrote (data minimization)."""
    doc_ref.update(
        {
            "status": status,
            "decided_at": datetime.now(timezone.utc),
            "content": firestore.DELETE_FIELD,
        }
    )


def approve_pending_fact(tenant_id: str, pending_fact_id: str, owner_uid: str) -> None:
    """Turn a pending fact into a real one via the normal publish path
    (src.facts.publisher.publish_fact), then mark the staged copy approved.

    Args:
        tenant_id (str): The project identifier, e.g. "my_project".
        pending_fact_id (str): The staged fact's document id within that
            project.
    """
    get_owned_tenant(tenant_id, owner_uid)
    doc_ref = _collection(tenant_id).document(pending_fact_id)
    doc = doc_ref.get()
    if not doc.exists or not _is_pending(doc.to_dict()):
        raise ValueError(f"No pending fact '{pending_fact_id}' for tenant '{tenant_id}'.")

    data = doc.to_dict()
    publish_fact(
        tenant_id, data["content"], data["category"], owner_uid, source=data.get("source", "chat")
    )
    _decide(doc_ref, APPROVED)


def reject_pending_fact(tenant_id: str, pending_fact_id: str, owner_uid: str) -> None:
    """Discard a pending fact without ever publishing it, remembering that it
    was rejected. Rejecting one that is gone or already decided does nothing.

    Args:
        tenant_id (str): The project identifier, e.g. "my_project".
        pending_fact_id (str): The staged fact's document id within that
            project.
    """
    get_owned_tenant(tenant_id, owner_uid)
    doc_ref = _collection(tenant_id).document(pending_fact_id)
    doc = doc_ref.get()
    if doc.exists and _is_pending(doc.to_dict()):
        _decide(doc_ref, REJECTED)


def get_pending_fact_stats(tenant_id: str, owner_uid: str) -> dict:
    """How many staged facts are waiting, approved and rejected — the approval
    rate is approved / (approved + rejected). Counts start from when decisions
    began to be kept; earlier ones were deleted.

    Args:
        tenant_id (str): The project identifier, e.g. "my_project".
    """
    get_owned_tenant(tenant_id, owner_uid)
    counts = {PENDING: 0, APPROVED: 0, REJECTED: 0}
    for doc in _collection(tenant_id).select(["status"]).stream():
        counts[doc.to_dict().get("status", PENDING)] += 1
    return counts


def _short(text: str) -> str:
    if len(text) <= MAX_PENDING_CONTENT_CHARS:
        return text
    return text[: MAX_PENDING_CONTENT_CHARS - 1] + "…"


def get_pending_facts_summary(tenant_id: str, owner_uid: str) -> dict:
    """The oldest facts awaiting approval, for helping the user decide which
    to approve.

    Each carries "similar_to_saved": the text of an already saved fact that
    says (nearly) the same, decided by code (src.facts.similar_facts) rather than
    left to the model, or None. Read-only; the pending facts themselves are
    approved or rejected only by the user, in the Pending tab.

    Args:
        tenant_id (str): The project identifier, e.g. "my_project".

    Returns:
        {"pending": [{"content", "category", "similar_to_saved"}, ...],
        "truncated": bool} — "truncated" is true when more are waiting.
    """
    pending = list_pending_facts(tenant_id, owner_uid)
    saved = get_tenant_facts(tenant_id, owner_uid)
    shown = pending[:MAX_PENDING_FOR_REVIEW]
    summary = []
    for fact in shown:
        similar = find_similar_facts(fact["content"] or "", saved)
        summary.append(
            {
                "content": _short(fact["content"] or ""),
                "category": fact["category"],
                "similar_to_saved": similar[0]["content"] if similar else None,
            }
        )
    return {"pending": summary, "truncated": len(pending) > MAX_PENDING_FOR_REVIEW}
