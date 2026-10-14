"""
Re-send a till row to the Main PC when it changes after it was pushed (#677).

A till pushes every row with ``synced = False`` and flips it to ``True``
once the Main PC acknowledges the push. Nothing used to flip it back, so a
change made later -- voiding a sale, committing a draft GRN, closing a
shift -- never reached the Main PC. The Main PC already applies a re-sent
row in place (found again through ``sync_id_map``), so all a till needs is
to mark the row unsynced again whenever one of its columns changes.

That is done here once, for every session, in a ``before_flush`` hook,
rather than in each service that edits a pushed row:

- A row with a ``synced`` column whose other columns changed goes back to
  ``synced = False`` -- unless the same flush sets ``synced`` itself (the
  sync client marking a row synced, or the Main PC storing a pushed row).
- A sale's items/payments and a purchase's items are pushed together with
  their document, so a change to one of them re-sends the document.

Customers are deliberately left out: a till pushes the customers it
*creates* (#680), but the Main PC owns customer details, and a pulled
customer's local id is already the Main PC id, so re-sending an edit would
be mistaken for a new customer.
"""

import logging
from typing import Any

from sqlalchemy import event
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# Set ``session.info[SKIP_CHANGE_TRACKING] = True`` on a session whose writes
# must not mark rows for re-sending (the Main PC applying a till's push).
SKIP_CHANGE_TRACKING = "cbpos_sync_skip_change_tracking"

# Tables whose ``synced`` flag only tracks the row's first push.
_CREATE_ONLY_TABLES = frozenset({"customers"})

# Child table -> relationship to the document it is pushed with.
_CHILD_PARENT: dict[str, str] = {
    "sale_items": "sale",
    "sale_payments": "sale",
    "purchase_items": "purchase",
}


def _has_sync_flag(obj: Any) -> bool:
    """True for a mapped row with a ``synced`` column that is re-sent when it changes."""
    mapper = sa_inspect(type(obj), raiseerr=False)
    if mapper is None or "synced" not in mapper.column_attrs:
        return False
    return mapper.local_table.name not in _CREATE_ONLY_TABLES


def _columns_changed(obj: Any) -> bool:
    """True if a column other than ``synced`` has a pending change."""
    state = sa_inspect(obj)
    for attr in state.mapper.column_attrs:
        if attr.key == "synced":
            continue
        if state.attrs[attr.key].history.has_changes():
            return True
    return False


def _synced_set_in_this_flush(obj: Any) -> bool:
    return sa_inspect(obj).attrs["synced"].history.has_changes()


def _mark_unsynced(obj: Any) -> None:
    """Flag an already-pushed row for re-sending, unless ``synced`` is being set explicitly."""
    if obj is None or not getattr(obj, "synced", False) or _synced_set_in_this_flush(obj):
        return
    obj.synced = False
    logger.debug(
        "Sync: %s%s changed after it was pushed; queued to re-send", type(obj).__name__, sa_inspect(obj).identity
    )


def _parent_of(session: Session, child: Any, relationship: str) -> Any | None:
    parent = getattr(child, relationship, None)
    if parent is not None:
        return parent
    mapper = sa_inspect(type(child))
    fk_column = next(iter(mapper.relationships[relationship].local_columns)).key
    parent_id = getattr(child, fk_column, None)
    if parent_id is None:
        return None
    return session.get(mapper.relationships[relationship].mapper.class_, parent_id)


@event.listens_for(Session, "before_flush")
def flag_changed_rows_for_resend(session: Session, flush_context: Any, instances: Any) -> None:
    """Mark pushed rows (or the document of a pushed child) unsynced when they change."""
    if session.info.get(SKIP_CHANGE_TRACKING):
        return

    for obj in list(session.dirty):
        if _has_sync_flag(obj) and _columns_changed(obj):
            _mark_unsynced(obj)

    for obj in list(session.new) + list(session.dirty):
        relationship = _CHILD_PARENT.get(getattr(obj, "__tablename__", ""))
        if relationship is None:
            continue
        if obj in session.new or _columns_changed(obj):
            _mark_unsynced(_parent_of(session, obj, relationship))

    for obj in session.deleted:
        if _CHILD_PARENT.get(getattr(obj, "__tablename__", "")) or _has_sync_flag(obj):
            # The Main PC never deletes a pushed row; it keeps its copy.
            logger.debug(
                "Sync: deleted %s%s is not propagated to the Main PC", type(obj).__name__, sa_inspect(obj).identity
            )
