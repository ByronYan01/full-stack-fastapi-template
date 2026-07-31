import uuid

from fastapi.testclient import TestClient
from sqlmodel import Session

from app import crud
from app.core.config import settings
from tests.utils.item import create_item_with_title, create_random_item


def test_create_item(
    client: TestClient, superuser_token_headers: dict[str, str]
) -> None:
    data = {"title": "Foo", "description": "Fighters"}
    response = client.post(
        f"{settings.API_V1_STR}/items/",
        headers=superuser_token_headers,
        json=data,
    )
    assert response.status_code == 200
    content = response.json()
    assert content["title"] == data["title"]
    assert content["description"] == data["description"]
    assert "id" in content
    assert "owner_id" in content


def test_read_item(
    client: TestClient, superuser_token_headers: dict[str, str], db: Session
) -> None:
    item = create_random_item(db)
    response = client.get(
        f"{settings.API_V1_STR}/items/{item.id}",
        headers=superuser_token_headers,
    )
    assert response.status_code == 200
    content = response.json()
    assert content["title"] == item.title
    assert content["description"] == item.description
    assert content["id"] == str(item.id)
    assert content["owner_id"] == str(item.owner_id)


def test_read_item_not_found(
    client: TestClient, superuser_token_headers: dict[str, str]
) -> None:
    response = client.get(
        f"{settings.API_V1_STR}/items/{uuid.uuid4()}",
        headers=superuser_token_headers,
    )
    assert response.status_code == 404
    content = response.json()
    assert content["detail"] == "Item not found"


def test_read_item_not_enough_permissions(
    client: TestClient, normal_user_token_headers: dict[str, str], db: Session
) -> None:
    item = create_random_item(db)
    response = client.get(
        f"{settings.API_V1_STR}/items/{item.id}",
        headers=normal_user_token_headers,
    )
    assert response.status_code == 403
    content = response.json()
    assert content["detail"] == "Not enough permissions"


def test_read_items(
    client: TestClient, superuser_token_headers: dict[str, str], db: Session
) -> None:
    create_random_item(db)
    create_random_item(db)
    response = client.get(
        f"{settings.API_V1_STR}/items/",
        headers=superuser_token_headers,
    )
    assert response.status_code == 200
    content = response.json()
    assert len(content["data"]) >= 2


def test_read_items_title_filter(
    client: TestClient, superuser_token_headers: dict[str, str], db: Session
) -> None:
    """
    Superuser fuzzy-searches by title (case-insensitive ILIKE). The mixed-case
    query verifies that the search is not case-sensitive.
    """
    create_item_with_title(db, title="AlphaProbe Item")
    create_item_with_title(db, title="BetaProbe Item")
    response = client.get(
        f"{settings.API_V1_STR}/items/?title=aLpHaPrObE",
        headers=superuser_token_headers,
    )
    assert response.status_code == 200
    data = response.json()
    titles = [it["title"] for it in data["data"]]
    assert any("AlphaProbe" in t for t in titles)
    assert not any("BetaProbe" in t for t in titles)


def test_read_items_pagination(
    client: TestClient, superuser_token_headers: dict[str, str], db: Session
) -> None:
    """
    skip/limit return disjoint slices; count reflects the full match set.
    """
    create_item_with_title(db, title="PaginatorProbe-A")
    create_item_with_title(db, title="PaginatorProbe-B")
    create_item_with_title(db, title="PaginatorProbe-C")
    base = f"{settings.API_V1_STR}/items/?title=PaginatorProbe"
    r1 = client.get(
        f"{base}&order=asc&skip=0&limit=1",
        headers=superuser_token_headers,
    )
    r2 = client.get(
        f"{base}&order=asc&skip=1&limit=1",
        headers=superuser_token_headers,
    )
    assert r1.status_code == 200
    assert r2.status_code == 200
    page1 = r1.json()
    page2 = r2.json()
    assert page1["count"] == page2["count"]
    assert page1["count"] >= 3
    # Same ordering, different offsets → different rows.
    if page1["data"] and page2["data"]:
        assert page1["data"][0]["id"] != page2["data"][0]["id"]


def test_read_items_default_limit(
    client: TestClient, superuser_token_headers: dict[str, str]
) -> None:
    """
    Omitting limit yields at most the default page size (10).
    """
    response = client.get(
        f"{settings.API_V1_STR}/items/",
        headers=superuser_token_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data["data"]) <= 10


def test_read_items_sort_order_asc_desc(
    client: TestClient, superuser_token_headers: dict[str, str], db: Session
) -> None:
    """
    order=asc / order=desc return rows in opposite created_at order.
    """
    first = create_item_with_title(db, title="OrderProbe-First")
    second = create_item_with_title(db, title="OrderProbe-Second")
    base = f"{settings.API_V1_STR}/items/?title=OrderProbe"
    r_desc = client.get(f"{base}&order=desc", headers=superuser_token_headers)
    r_asc = client.get(f"{base}&order=asc", headers=superuser_token_headers)
    assert r_desc.status_code == 200
    assert r_asc.status_code == 200

    def find_index(rows: list[dict[str, object]], item_id: uuid.UUID) -> int | None:
        target = str(item_id)
        for i, row in enumerate(rows):
            if row["id"] == target:
                return i
        return None

    desc_rows = r_desc.json()["data"]
    asc_rows = r_asc.json()["data"]
    desc_first = find_index(desc_rows, first.id)
    desc_second = find_index(desc_rows, second.id)
    asc_first = find_index(asc_rows, first.id)
    asc_second = find_index(asc_rows, second.id)
    # Both probes must be present in each page.
    assert desc_first is not None
    assert desc_second is not None
    assert asc_first is not None
    assert asc_second is not None
    # second was created after first → desc puts second earlier, asc puts first earlier.
    assert desc_second < desc_first
    assert asc_first < asc_second


def test_read_items_invalid_order(
    client: TestClient, superuser_token_headers: dict[str, str]
) -> None:
    """
    order must be one of 'asc' | 'desc'; otherwise 422.
    """
    response = client.get(
        f"{settings.API_V1_STR}/items/?order=invalid",
        headers=superuser_token_headers,
    )
    assert response.status_code == 422


def test_read_items_invalid_limit(
    client: TestClient, superuser_token_headers: dict[str, str]
) -> None:
    """
    limit must be 1..100; otherwise 422.
    """
    r_zero = client.get(
        f"{settings.API_V1_STR}/items/?limit=0",
        headers=superuser_token_headers,
    )
    r_huge = client.get(
        f"{settings.API_V1_STR}/items/?limit=999",
        headers=superuser_token_headers,
    )
    assert r_zero.status_code == 422
    assert r_huge.status_code == 422


def test_read_items_title_filter_normal_user(
    client: TestClient,
    normal_user_token_headers: dict[str, str],
    db: Session,
) -> None:
    """
    Normal users can only search within items they own — never see items
    belonging to other users even when the title matches.
    """
    # Item owned by a random (different) user — must NOT be visible.
    create_item_with_title(db, title="LeakProbe-Other-Owner")
    # Item owned by the test (normal) user — should be searchable.
    normal_user = crud.get_user_by_email(session=db, email=settings.EMAIL_TEST_USER)
    assert normal_user is not None
    assert normal_user.id is not None
    create_item_with_title(
        db, title="LeakProbe-Mine", owner_id=normal_user.id
    )
    response = client.get(
        f"{settings.API_V1_STR}/items/?title=LeakProbe",
        headers=normal_user_token_headers,
    )
    assert response.status_code == 200
    titles = [it["title"] for it in response.json()["data"]]
    assert "LeakProbe-Mine" in titles
    assert "LeakProbe-Other-Owner" not in titles


def test_update_item(
    client: TestClient, superuser_token_headers: dict[str, str], db: Session
) -> None:
    item = create_random_item(db)
    data = {"title": "Updated title", "description": "Updated description"}
    response = client.put(
        f"{settings.API_V1_STR}/items/{item.id}",
        headers=superuser_token_headers,
        json=data,
    )
    assert response.status_code == 200
    content = response.json()
    assert content["title"] == data["title"]
    assert content["description"] == data["description"]
    assert content["id"] == str(item.id)
    assert content["owner_id"] == str(item.owner_id)


def test_update_item_not_found(
    client: TestClient, superuser_token_headers: dict[str, str]
) -> None:
    data = {"title": "Updated title", "description": "Updated description"}
    response = client.put(
        f"{settings.API_V1_STR}/items/{uuid.uuid4()}",
        headers=superuser_token_headers,
        json=data,
    )
    assert response.status_code == 404
    content = response.json()
    assert content["detail"] == "Item not found"


def test_update_item_not_enough_permissions(
    client: TestClient, normal_user_token_headers: dict[str, str], db: Session
) -> None:
    item = create_random_item(db)
    data = {"title": "Updated title", "description": "Updated description"}
    response = client.put(
        f"{settings.API_V1_STR}/items/{item.id}",
        headers=normal_user_token_headers,
        json=data,
    )
    assert response.status_code == 403
    content = response.json()
    assert content["detail"] == "Not enough permissions"


def test_delete_item(
    client: TestClient, superuser_token_headers: dict[str, str], db: Session
) -> None:
    item = create_random_item(db)
    response = client.delete(
        f"{settings.API_V1_STR}/items/{item.id}",
        headers=superuser_token_headers,
    )
    assert response.status_code == 200
    content = response.json()
    assert content["message"] == "Item deleted successfully"


def test_delete_item_not_found(
    client: TestClient, superuser_token_headers: dict[str, str]
) -> None:
    response = client.delete(
        f"{settings.API_V1_STR}/items/{uuid.uuid4()}",
        headers=superuser_token_headers,
    )
    assert response.status_code == 404
    content = response.json()
    assert content["detail"] == "Item not found"


def test_delete_item_not_enough_permissions(
    client: TestClient, normal_user_token_headers: dict[str, str], db: Session
) -> None:
    item = create_random_item(db)
    response = client.delete(
        f"{settings.API_V1_STR}/items/{item.id}",
        headers=normal_user_token_headers,
    )
    assert response.status_code == 403
    content = response.json()
    assert content["detail"] == "Not enough permissions"
