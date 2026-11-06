"""reparent_nested_categories (Phase 4 #921)

Revision ID: 61b23204d804
Revises: 5c6d7e8f9a0b
Create Date: 2026-11-06 21:45:35.639529

"""

import logging
from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "61b23204d804"
down_revision: Union[str, None] = "5c6d7e8f9a0b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

logger = logging.getLogger(__name__)


def reparent_grandchildren(bind) -> int:
    """Re-parent any grandchild or deeper category to its top-level ancestor.

    Returns the number of re-parented categories.
    """
    insp = sa.inspect(bind)
    existing_tables = set(insp.get_table_names())
    if "categories" not in existing_tables:
        return 0

    categories = sa.table(
        "categories",
        sa.column("id", sa.Integer),
        sa.column("name", sa.String),
        sa.column("parent_id", sa.Integer),
    )

    rows = bind.execute(sa.select(categories.c.id, categories.c.name, categories.c.parent_id)).all()
    if not rows:
        return 0

    cat_map = {row.id: (row.name, row.parent_id) for row in rows}

    def get_top_level_ancestor(cat_id: int) -> int | None:
        curr = cat_id
        depth = 0
        while curr in cat_map:
            _name, parent_id = cat_map[curr]
            if parent_id is None:
                return curr if depth > 0 else None
            curr = parent_id
            depth += 1
            if depth > 100:  # cycle safeguard
                break
        return None

    reparented_count = 0
    for cat_id, (name, parent_id) in cat_map.items():
        if parent_id is not None:
            parent_info = cat_map.get(parent_id)
            if parent_info and parent_info[1] is not None:
                root_id = get_top_level_ancestor(cat_id)
                if root_id and root_id != parent_id:
                    logger.info(
                        "Re-parenting category '%s' (ID %d) from parent %d to top-level ancestor %d",
                        name,
                        cat_id,
                        parent_id,
                        root_id,
                    )
                    bind.execute(categories.update().where(categories.c.id == cat_id).values(parent_id=root_id))
                    reparented_count += 1

    return reparented_count


def upgrade() -> None:
    bind = op.get_bind()
    reparent_grandchildren(bind)


def downgrade() -> None:
    pass
