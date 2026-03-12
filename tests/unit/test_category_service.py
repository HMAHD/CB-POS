"""
Unit tests for CategoryService — CRUD operations and hierarchy.
"""

import pytest

from cbpos.core.services.category_service import CategoryService
from cbpos.core.models import Category, Product


# ── Shared Fixtures ──────────────────────────────────────────────────────

_counter = 0


def _next_suffix() -> str:
    global _counter
    _counter += 1
    return str(_counter)


@pytest.fixture
def test_category(db_session):
    """Create a test category."""
    suffix = _next_suffix()
    cat = Category(name=f"TestCat_{suffix}", color="#FF0000")
    db_session.add(cat)
    db_session.flush()
    return cat


# ── Test: create ─────────────────────────────────────────────────────────


def test_create_category(db_session):
    """Creating a category sets name and color."""
    suffix = _next_suffix()
    cat = CategoryService.create(name=f"Groceries_{suffix}", color="#00FF00")

    assert cat is not None
    assert cat.name == f"Groceries_{suffix}"
    assert cat.color == "#00FF00"


def test_create_duplicate_name(db_session, test_category):
    """Creating a category with an existing name raises ValueError."""
    with pytest.raises(ValueError, match="already exists"):
        CategoryService.create(name=test_category.name)


# ── Test: update ─────────────────────────────────────────────────────────


def test_update_category(db_session, test_category):
    """Updating a category changes name and color."""
    suffix = _next_suffix()
    new_name = f"UpdatedCat_{suffix}"
    updated = CategoryService.update(test_category.id, name=new_name, color="#0000FF")

    assert updated.name == new_name
    assert updated.color == "#0000FF"


# ── Test: delete ─────────────────────────────────────────────────────────


def test_delete_category(db_session, test_category):
    """Deleting a category with no products succeeds."""
    cat_id = test_category.id
    CategoryService.delete(cat_id)

    # Verify it is gone
    result = db_session.get(Category, cat_id)
    assert result is None


def test_delete_category_with_products(db_session, test_category):
    """Deleting a category that has products raises ValueError."""
    suffix = _next_suffix()
    product = Product(
        name_en=f"Product_{suffix}",
        barcode="DEL{:0>4}".format(suffix),
        price=100.0,
        stock_qty=5.0,
        category_id=test_category.id,
    )
    db_session.add(product)
    db_session.flush()

    with pytest.raises(ValueError, match="product"):
        CategoryService.delete(test_category.id)


# ── Test: get_descendant_ids ─────────────────────────────────────────────


def test_get_descendant_ids(db_session):
    """get_descendant_ids returns all descendant category IDs."""
    suffix = _next_suffix()

    # Create a tree: root -> child1, child2; child1 -> grandchild
    root = Category(name=f"Root_{suffix}", color="#FFFFFF")
    db_session.add(root)
    db_session.flush()

    child1 = Category(name=f"Child1_{suffix}", color="#AAAAAA", parent_id=root.id)
    child2 = Category(name=f"Child2_{suffix}", color="#BBBBBB", parent_id=root.id)
    db_session.add_all([child1, child2])
    db_session.flush()

    grandchild = Category(name=f"GrandChild_{suffix}", color="#CCCCCC", parent_id=child1.id)
    db_session.add(grandchild)
    db_session.flush()

    descendants = CategoryService.get_descendant_ids(root.id)

    assert child1.id in descendants
    assert child2.id in descendants
    assert grandchild.id in descendants
    assert root.id not in descendants
    assert len(descendants) == 3
