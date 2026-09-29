"""A project's saved facts: list them, and the edit and delete that a chat
proposal card's button calls."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from api.deps import get_current_owner_uid
from src.facts.facts import delete_fact, get_fact, get_tenant_facts, update_fact

router = APIRouter()


class FactUpdate(BaseModel):
    """Request body for PATCH .../facts/{fact_id}: the fields to change,
    omitting either one to leave it as is."""

    model_config = ConfigDict(extra="forbid")

    # Omitted means unchanged, same as update_fact — but an empty body would
    # change nothing, so it is refused below.
    content: str | None = Field(default=None, strict=True, min_length=1, max_length=2000)
    category: str | None = Field(default=None, strict=True, min_length=1, max_length=50)


@router.get("/tenants/{tenant_id}/facts")
def get_facts(tenant_id: str, owner_uid: str = Depends(get_current_owner_uid)) -> list[dict]:
    """Return every fact stored for the project — the Facts tab's data
    source (see get_tenant_facts for the shape of each entry)."""
    return get_tenant_facts(tenant_id, owner_uid)


# What a chat proposal card's button calls: the model only ever
# proposes an edit or a delete, and the user's click is what makes it.
@router.patch("/tenants/{tenant_id}/facts/{fact_id}")
def edit_fact(
    tenant_id: str, fact_id: str, body: FactUpdate, owner_uid: str = Depends(get_current_owner_uid)
) -> dict:
    """Apply a partial update to one fact and confirm it was updated.

    Args:
        fact_id (str): The fact's document id, as returned by
            get_tenant_facts.

    Raises:
        HTTPException: 422 if neither content nor category is given, 404 if
            the fact doesn't exist, 400 if the new category is invalid.
    """
    if body.content is None and body.category is None:
        raise HTTPException(status_code=422, detail="Give a content or a category to change")
    try:
        get_fact(tenant_id, fact_id, owner_uid)
        update_fact(tenant_id, fact_id, owner_uid, content=body.content, category=body.category)
    except (PermissionError, LookupError):
        raise HTTPException(status_code=404, detail="Fact not found")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"status": "updated"}


@router.delete("/tenants/{tenant_id}/facts/{fact_id}")
def remove_fact(tenant_id: str, fact_id: str, owner_uid: str = Depends(get_current_owner_uid)) -> dict:
    """Delete one fact and confirm it was deleted.

    Args:
        fact_id (str): The fact's document id, as returned by
            get_tenant_facts.

    Raises:
        HTTPException: 404 if the fact doesn't exist.
    """
    try:
        get_fact(tenant_id, fact_id, owner_uid)
        delete_fact(tenant_id, fact_id, owner_uid)
    except (PermissionError, LookupError):
        raise HTTPException(status_code=404, detail="Fact not found")
    return {"status": "deleted"}
