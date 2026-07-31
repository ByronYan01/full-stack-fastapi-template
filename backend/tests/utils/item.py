import uuid

from sqlmodel import Session

from app import crud
from app.models import Item, ItemCreate
from tests.utils.user import create_random_user
from tests.utils.utils import random_lower_string


def create_random_item(db: Session) -> Item:
    user = create_random_user(db)
    owner_id = user.id
    assert owner_id is not None
    title = random_lower_string()
    description = random_lower_string()
    item_in = ItemCreate(title=title, description=description)
    return crud.create_item(session=db, item_in=item_in, owner_id=owner_id)


def create_item_with_title(
    db: Session, title: str, owner_id: uuid.UUID | None = None
) -> Item:
    """
    Create an item with a deterministic title (and optional explicit owner).

    Used by the read_items search/sort/pagination tests that need to assert
    on known title values rather than random strings.
    """
    if owner_id is None:
        owner_id = create_random_user(db).id
    assert owner_id is not None
    item_in = ItemCreate(title=title)
    return crud.create_item(session=db, item_in=item_in, owner_id=owner_id)
