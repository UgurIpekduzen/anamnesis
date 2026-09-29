"""Facts staged from GitHub activity, waiting for the user to approve or reject
them, and how often they approve."""

from fastapi import APIRouter, Depends, HTTPException

from api.deps import get_current_owner_uid
from src.facts.categories import InvalidCategory

router = APIRouter()


# Lazily-importing wrappers (same pattern as get_runner/
# restore_session in the chat router): src.facts.pending_facts pulls in
# google-cloud-pubsub (via src.facts.publisher, for the approve path), which
# only these endpoints need — deferring it keeps it off every other request's
# startup cost. Real module-level names so
# test/test_api_pending_facts.py's monkeypatch.setattr(pending, ...)
# still works.
def list_pending_facts(tenant_id: str, owner_uid: str) -> list[dict]:
    from src.facts.pending_facts import list_pending_facts as _list_pending_facts

    return _list_pending_facts(tenant_id, owner_uid)


def approve_pending_fact(tenant_id: str, pending_fact_id: str, owner_uid: str) -> None:
    from src.facts.pending_facts import approve_pending_fact as _approve_pending_fact

    return _approve_pending_fact(tenant_id, pending_fact_id, owner_uid)


def reject_pending_fact(tenant_id: str, pending_fact_id: str, owner_uid: str) -> None:
    from src.facts.pending_facts import reject_pending_fact as _reject_pending_fact

    return _reject_pending_fact(tenant_id, pending_fact_id, owner_uid)


def get_pending_fact_stats(tenant_id: str, owner_uid: str) -> dict:
    from src.facts.pending_facts import get_pending_fact_stats as _get_pending_fact_stats

    return _get_pending_fact_stats(tenant_id, owner_uid)


@router.get("/tenants/{tenant_id}/pending_facts")
def get_pending_facts(tenant_id: str, owner_uid: str = Depends(get_current_owner_uid)) -> list[dict]:
    try:
        return list_pending_facts(tenant_id, owner_uid)
    except PermissionError:
        raise HTTPException(status_code=404, detail="Project not found")


@router.get("/tenants/{tenant_id}/pending_facts/stats")
def get_pending_facts_stats(tenant_id: str, owner_uid: str = Depends(get_current_owner_uid)) -> dict:
    try:
        return get_pending_fact_stats(tenant_id, owner_uid)
    except PermissionError:
        raise HTTPException(status_code=404, detail="Project not found")


@router.post("/tenants/{tenant_id}/pending_facts/{pending_fact_id}/approve")
def approve_pending_fact_endpoint(
    tenant_id: str, pending_fact_id: str, owner_uid: str = Depends(get_current_owner_uid)
) -> dict:
    try:
        approve_pending_fact(tenant_id, pending_fact_id, owner_uid)
    except PermissionError:
        raise HTTPException(status_code=404, detail="Project not found")
    except InvalidCategory as exc:
        # The user removed this fact's category after it was staged.
        raise HTTPException(status_code=400, detail=str(exc))
    except ValueError:
        raise HTTPException(status_code=404, detail="Pending fact not found")
    return {"status": "approved"}


@router.delete("/tenants/{tenant_id}/pending_facts/{pending_fact_id}")
def reject_pending_fact_endpoint(
    tenant_id: str, pending_fact_id: str, owner_uid: str = Depends(get_current_owner_uid)
) -> dict:
    try:
        reject_pending_fact(tenant_id, pending_fact_id, owner_uid)
    except PermissionError:
        raise HTTPException(status_code=404, detail="Project not found")
    return {"status": "rejected"}
