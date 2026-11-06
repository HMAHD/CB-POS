import importlib.util
from pathlib import Path

import pytest

from cbpos.core.models import Category, Product
from cbpos.core.services.category_service import CategoryService

_migration_path = (
    Path(__file__).resolve().parents[2] / "alembic" / "versions" / "61b23204d804_reparent_nested_categories.py"
)
_spec = importlib.util.spec_from_file_location("migration_61b23204d804", _migration_path)
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)
reparent_grandchildren = _migration.reparent_grandchildren

_counter = 0


def _uid() -> str:
    global _counter
    _counter += 1
    return str(_counter)


def test_issue_921_parent_must_be_top_level(db_session):
    """CategoryService.create and update reject parents that are not top-level (#921)."""
    uid = _uid()
    root = CategoryService.create(name=f"Beverages_{uid}", parent_id=None)
    sub = CategoryService.create(name=f"Soft Drinks_{uid}", parent_id=root.id)

    # Creating a grandchild (sub as parent) must be rejected
    with pytest.raises(ValueError, match="category_too_deep"):
        CategoryService.create(name=f"Coke_{uid}", parent_id=sub.id)

    # Creating an independent category then updating its parent to sub must be rejected
    coke = CategoryService.create(name=f"Coke_{uid}", parent_id=None)
    with pytest.raises(ValueError, match="category_too_deep"):
        CategoryService.update(coke.id, parent_id=sub.id)

    # A category that has subcategories cannot be made a child of another category
    with pytest.raises(ValueError, match="category_too_deep"):
        CategoryService.update(root.id, parent_id=coke.id)


def test_issue_921_migration_reparents_grandchildren(db_session):
    """Data migration re-parents any grandchild to its top-level ancestor, preserving products (#921)."""
    uid = _uid()

    # Manually bypass service check to simulate legacy database state with 4 levels
    grandparent = Category(name=f"Level1_{uid}", parent_id=None)
    db_session.add(grandparent)
    db_session.flush()

    parent = Category(name=f"Level2_{uid}", parent_id=grandparent.id)
    db_session.add(parent)
    db_session.flush()

    grandchild = Category(name=f"Level3_{uid}", parent_id=parent.id)
    db_session.add(grandchild)
    db_session.flush()

    great_grandchild = Category(name=f"Level4_{uid}", parent_id=grandchild.id)
    db_session.add(great_grandchild)
    db_session.flush()

    # Attach a product to grandchild
    product = Product(
        name_en=f"Item_{uid}",
        barcode=f"BAR{uid:0>6}",
        price=150.0,
        stock_qty=10.0,
        category_id=grandchild.id,
    )
    db_session.add(product)
    db_session.commit()

    # Execute data migration
    reparented = reparent_grandchildren(db_session.connection())
    db_session.commit()

    assert reparented >= 2

    # Refresh objects from database
    db_session.refresh(grandparent)
    db_session.refresh(parent)
    db_session.refresh(grandchild)
    db_session.refresh(great_grandchild)
    db_session.refresh(product)

    # Level 1 and Level 2 remain unchanged
    assert grandparent.parent_id is None
    assert parent.parent_id == grandparent.id

    # Level 3 and Level 4 must now point directly to Level 1 (top-level ancestor)
    assert grandchild.parent_id == grandparent.id
    assert great_grandchild.parent_id == grandparent.id

    # Product must still belong to grandchild
    assert product.category_id == grandchild.id
