import uuid
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query
from sqlmodel import col, func, select

from app.api.deps import CurrentUser, SessionDep
from app.models import (
    Item,
    ItemCreate,
    ItemPublic,
    ItemsPublic,
    ItemUpdate,
    Message,
    User,
)

router = APIRouter(prefix="/items", tags=["items"])


def _apply_item_filters(
    statement: Any, *, current_user: User, title: str | None
) -> Any:
    """
    Apply shared filter clauses (title ILIKE + owner scoping) to the given
    select statement. Used by both the count and the list queries so that
    where-conditions cannot drift apart (DRY).

    Typed as ``Any`` because SQLModel's ``select(Item)`` returns a
    ``SelectOfScalar[Item]`` whose precise generic doesn't survive being
    threaded through a helper function under mypy; the runtime behaviour is
    unchanged.
    """
    if title:
        statement = statement.where(col(Item.title).ilike(f"%{title}%"))
    if not current_user.is_superuser:
        statement = statement.where(Item.owner_id == current_user.id)
    return statement


@router.get("/", response_model=ItemsPublic)
def read_items(
    session: SessionDep,
    current_user: CurrentUser,
    title: str | None = Query(default=None, max_length=255),
    order: Literal["asc", "desc"] = Query(default="desc"),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=10, ge=1, le=100),
) -> Any:
    """
    Retrieve items with optional title search, ordering and pagination.
    """
    base = _apply_item_filters(
        select(Item), current_user=current_user, title=title
    )

    count_statement = select(func.count()).select_from(base.subquery())
    count = session.scalar(count_statement) or 0

    order_clause = (
        col(Item.created_at).desc()
        if order == "desc"
        else col(Item.created_at).asc()
    )
    rows_statement = base.order_by(order_clause).offset(skip).limit(limit)
    items = session.exec(rows_statement).all()

    items_public = [ItemPublic.model_validate(item) for item in items]
    return ItemsPublic(data=items_public, count=count)


@router.get("/{id}", response_model=ItemPublic)
def read_item(session: SessionDep, current_user: CurrentUser, id: uuid.UUID) -> Any:
    """
    Get item by ID.
    """
    item = session.get(Item, id)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    if not current_user.is_superuser and (item.owner_id != current_user.id):
        raise HTTPException(status_code=403, detail="Not enough permissions")
    return item


@router.post("/", response_model=ItemPublic)
def create_item(
    *, session: SessionDep, current_user: CurrentUser, item_in: ItemCreate
) -> Any:
    """
    Create new item.
    """
    item = Item.model_validate(item_in, update={"owner_id": current_user.id})
    session.add(item)
    session.commit()
    session.refresh(item)
    return item


@router.put("/{id}", response_model=ItemPublic)
def update_item(
    *,
    session: SessionDep,
    current_user: CurrentUser,
    id: uuid.UUID,
    item_in: ItemUpdate,
) -> Any:
    """
    Update an item.
    """
    item = session.get(Item, id)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    if not current_user.is_superuser and (item.owner_id != current_user.id):
        raise HTTPException(status_code=403, detail="Not enough permissions")
    update_dict = item_in.model_dump(exclude_unset=True)
    item.sqlmodel_update(update_dict)
    session.add(item)
    session.commit()
    session.refresh(item)
    return item


@router.delete("/{id}")
def delete_item(
    session: SessionDep, current_user: CurrentUser, id: uuid.UUID
) -> Message:
    """
    Delete an item.
    """
    item = session.get(Item, id)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    if not current_user.is_superuser and (item.owner_id != current_user.id):
        raise HTTPException(status_code=403, detail="Not enough permissions")
    session.delete(item)
    session.commit()
    return Message(message="Item deleted successfully")
