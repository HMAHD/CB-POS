"""
Till side of #680: renumber a till-created customer to its Main PC id.

Customers are a catalog table: tills pull them from the Main PC by id. A
customer created on a till got the till's next free id, which the Main PC
may already use for a different customer -- the next catalog pull would
then overwrite the till's customer, and every sale pointing at it would
silently move to someone else. So once the Main PC has stored a pushed
customer (and said which id it got), the till moves its row, and every
row pointing at it, to that id. From then on the till and the Main PC
agree on the customer's id, like any pulled customer.
"""

import logging
from typing import Any

from sqlalchemy import Table, delete, func, insert, select, update

from cbpos.core.database import Base
from cbpos.core.models import Customer

logger = logging.getLogger(__name__)

# Columns unique per customer: cleared on the copy while both rows exist.
_UNIQUE_COLUMNS = ("phone", "loyalty_card_code")


def _customer_references() -> list[tuple[Table, Any]]:
    """Every (table, column) with a foreign key to customers.id."""
    customers = Customer.__table__
    refs = []
    for table in Base.metadata.sorted_tables:
        for fk in table.foreign_keys:
            if fk.column.table is customers:
                refs.append((table, fk.parent))
    return refs


def _repoint(session: Any, old_id: int, new_id: int) -> None:
    for table, column in _customer_references():
        session.execute(update(table).where(column == old_id).values({column.name: new_id}))


def _move(session: Any, old_id: int, new_id: int) -> None:
    """Give customer ``old_id`` the id ``new_id`` (which must be free), keeping every reference.

    Done as copy, repoint, delete -- never as an UPDATE of the primary key,
    which the rows pointing at the customer would block -- so it works
    with foreign keys enforced on any database.
    """
    table = Customer.__table__
    row = session.execute(select(table).where(table.c.id == old_id)).mappings().one()
    copy = dict(row)
    copy["id"] = new_id
    uniques = {c: copy[c] for c in _UNIQUE_COLUMNS}
    for column in _UNIQUE_COLUMNS:
        copy[column] = None
    session.execute(insert(table).values(copy))
    _repoint(session, old_id, new_id)
    session.execute(delete(table).where(table.c.id == old_id))
    session.execute(update(table).where(table.c.id == new_id).values(uniques))


def renumber_customers(session: Any, id_map: dict[int, int]) -> None:
    """Move each till-created customer to the id the Main PC gave it, and mark it synced.

    Args:
        session: Open session on the till database (the caller commits).
        id_map: ``{till id: Main PC id}`` from the push acknowledgement.
    """
    table = Customer.__table__
    pending = {local: server for local, server in id_map.items() if local != server}
    for local_id in id_map:
        if local_id not in pending:
            session.execute(update(table).where(table.c.id == local_id).values(synced=True))
    if not pending:
        return

    session.flush()
    # 1. Park every customer being moved on a temporary id, so moves that
    #    chain (51 -> 52 while 52 -> 53) never meet.
    parked: dict[int, int] = {}
    for local_id in pending:
        if session.execute(select(table.c.id).where(table.c.id == local_id)).first() is None:
            logger.warning("Sync: till customer %s no longer exists; nothing to renumber", local_id)
            continue
        parked[local_id] = -local_id
        _move(session, local_id, -local_id)

    # 2. Move each parked customer to its Main PC id.
    for local_id, temp_id in parked.items():
        server_id = pending[local_id]
        occupant = session.execute(select(table.c.id, table.c.synced).where(table.c.id == server_id)).first()
        if occupant is not None and occupant.synced:
            # The Main PC's own copy of this customer (it was already pulled,
            # or the Main PC matched it to a customer it had): one customer.
            _repoint(session, temp_id, server_id)
            session.execute(delete(table).where(table.c.id == temp_id))
            logger.info("Sync: till customer %s merged into Main PC customer %s", local_id, server_id)
            continue
        if occupant is not None:
            # Created on this till after the push was collected: not known to
            # the Main PC yet, so it can take any free id.
            top = max(session.execute(select(func.max(table.c.id))).scalar() or 0, max(pending.values()))
            _move(session, server_id, top + 1)
        _move(session, temp_id, server_id)
        session.execute(update(table).where(table.c.id == server_id).values(synced=True))
        logger.info("Sync: till customer %s is now customer %s", local_id, server_id)

    session.expire_all()
