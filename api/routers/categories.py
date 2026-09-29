"""The signed-in user's own list of fact categories."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from api.deps import get_current_owner_uid
from src.facts.categories import get_category_settings, reset_categories, save_categories

router = APIRouter()


class CategoriesUpdate(BaseModel):
    # forbid: an unknown field is a client bug. The list itself is checked in
    # src/facts/categories.py (length, names, duplicates); the cap here only keeps an
    # absurd request from being parsed at all.
    model_config = ConfigDict(extra="forbid")

    categories: list[str] = Field(max_length=50)


# The user's own categories: the suggested list until they change it.
@router.get("/categories")
def read_categories(owner_uid: str = Depends(get_current_owner_uid)) -> dict:
    return get_category_settings(owner_uid)


@router.put("/categories")
def update_categories(body: CategoriesUpdate, owner_uid: str = Depends(get_current_owner_uid)) -> dict:
    # owner_uid comes from the verified token, never the body.
    try:
        save_categories(owner_uid, body.categories)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return get_category_settings(owner_uid)


@router.delete("/categories")
def delete_categories(owner_uid: str = Depends(get_current_owner_uid)) -> dict:
    reset_categories(owner_uid)
    return get_category_settings(owner_uid)
