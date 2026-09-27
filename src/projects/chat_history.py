import os
from datetime import datetime, timedelta, timezone

from google.cloud import firestore

from src.core.firestore_client import get_client
from src.projects.tenants import CHAT_TURNS_COLLECTION, get_owned_tenant

# Saved conversation turns (APPCE-60): one document per *finished* turn,
# holding just the question and the final answer as text. Tool calls and
# their (often large) results are deliberately not stored — the model can
# call the tools again, and leaving them out keeps writes to one per turn
# and every stored slice cut on a whole-turn boundary.
#
# expire_at is what a Firestore TTL policy on this field keys off (a
# Terraform resource) to sweep abandoned conversations; it is also
# filtered on read, so an expired turn never resurfaces while the sweep —
# which can lag by a day or so — hasn't caught up yet.
RETENTION_DAYS = int(os.environ.get("CHAT_RETENTION_DAYS", 30))


def _turns_ref(tenant_id: str):
    return get_client().collection("tenants").document(tenant_id).collection(CHAT_TURNS_COLLECTION)


def append_turn(tenant_id: str, owner_uid: str, question: str, answer: str) -> None:
    """Save one finished turn under tenant_id.

    Raises:
        PermissionError: if the tenant isn't owner_uid's.
    """
    get_owned_tenant(tenant_id, owner_uid)
    now = datetime.now(timezone.utc)
    _turns_ref(tenant_id).add(
        {
            "question": question,
            "answer": answer,
            "created_at": now,
            "expire_at": now + timedelta(days=RETENTION_DAYS),
        }
    )


def load_recent_turns(tenant_id: str, owner_uid: str, limit: int) -> list[dict]:
    """Return up to `limit` of the most recent unexpired turns, oldest first.

    Raises:
        PermissionError: if the tenant isn't owner_uid's.
    """
    get_owned_tenant(tenant_id, owner_uid)
    if limit <= 0:
        return []

    # Order by created_at alone, not a range on expire_at: combining an
    # inequality on one field with an ordering on another needs a composite
    # index, and expiry is cheap to apply to at most `limit` rows here.
    now = datetime.now(timezone.utc)
    docs = _turns_ref(tenant_id).order_by("created_at", direction=firestore.Query.DESCENDING).limit(limit).stream()
    turns = [doc.to_dict() for doc in docs]
    live = [turn for turn in turns if turn["expire_at"] > now]
    return [
        {"question": turn["question"], "answer": turn["answer"], "created_at": turn["created_at"]}
        for turn in reversed(live)
    ]


def clear_turns(tenant_id: str, owner_uid: str) -> None:
    """Delete every saved turn under tenant_id.

    Raises:
        PermissionError: if the tenant isn't owner_uid's.
    """
    get_owned_tenant(tenant_id, owner_uid)
    for doc in _turns_ref(tenant_id).stream():
        doc.reference.delete()
