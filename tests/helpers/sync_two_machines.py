"""Two real databases -- a Main PC and a till -- wired through the real sync code.

``SyncClient`` runs against the till's database and its HTTP requests are
handed straight to the real ``SyncRequestHandler`` methods running against
the Main PC's database, round-tripped through JSON exactly as on the wire.
``Database()`` is pointed at whichever machine is "running" the code, so
services can be called on either side as they would be in the shop.
"""

import os
from collections.abc import Iterator
from contextlib import contextmanager
from decimal import Decimal
from typing import Any

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from cbpos.core.database import Base, Database
from cbpos.core.models import Permission, Product, Role, User
from cbpos.core.services.config_service import ConfigService
from cbpos.core.services.sync_protocol import (
    EP_PULL_CATALOG,
    EP_PULL_STOCK,
    EP_PUSH_TRANSACTIONS,
    EP_REGISTER,
    sync_json_dumps,
    sync_json_loads,
)
from cbpos.infrastructure.sync_client import SyncClient
from cbpos.infrastructure.sync_server import SyncRequestHandler


def make_machine_db() -> Database:
    """A standalone-mode ``Database`` on its own in-memory SQLite (foreign keys on, as in production)."""
    db = object.__new__(Database)
    db._db_mode = "standalone"
    db.engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool, echo=False)

    @event.listens_for(db.engine, "connect")
    def _pragmas(dbapi_conn: Any, _record: Any) -> None:
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    db.SessionLocal = sessionmaker(bind=db.engine, autocommit=False, autoflush=False, expire_on_commit=False)
    Base.metadata.create_all(bind=db.engine)

    import uuid

    from cbpos.core.models import LocalIdentity

    with db.SessionLocal() as session:
        session.add(LocalIdentity(db_instance_id=str(uuid.uuid4())))
        session.commit()
    return db


class _Handler:
    """Stand-in for SyncRequestHandler: the real handler methods, no socket."""

    def __init__(self, path: str, body: dict | None):
        self.path = path
        self._body = body
        self.client_address = ("127.0.0.1", 12345)
        self.response: dict | None = None
        self.status: int | None = None

    def _read_json(self) -> dict | None:
        return self._body

    def _send_json(self, data: Any, status: int = 200) -> None:
        # Through JSON, as the till would receive it.
        self.response = sync_json_loads(sync_json_dumps(data))
        self.status = status

    _handle_register = SyncRequestHandler._handle_register
    _handle_push_transactions = SyncRequestHandler._handle_push_transactions
    _handle_pull_catalog = SyncRequestHandler._handle_pull_catalog
    _handle_pull_stock = SyncRequestHandler._handle_pull_stock
    _log_sync = staticmethod(SyncRequestHandler._log_sync)


class Shop:
    """A Main PC and one or more tills sharing one process."""

    def __init__(self, settings_dir: str):
        self.main = make_machine_db()
        self.tills: dict[str, tuple[Database, SyncClient]] = {}
        self._settings_dir = settings_dir
        self.offline = False  # True: every request fails, like a pulled cable
        self.drop_responses = False  # True: the Main PC applies, the reply is lost

    # --- machines ---

    def add_till(self, terminal_id: str) -> SyncClient:
        db = make_machine_db()
        client = SyncClient(terminal_id, "127.0.0.1:1", shared_secret="")
        client._request = lambda method, endpoint, data=None, timeout=10: self._serve(method, endpoint, data)
        self.tills[terminal_id] = (db, client)
        return client

    @contextmanager
    def on(self, machine: str) -> Iterator[Database]:
        """Run the block "on" a machine: ``Database()`` is that machine's database."""
        db = self.main if machine == "main" else self.tills[machine][0]
        previous = Database._instance
        Database._instance = db
        try:
            yield db
        finally:
            Database._instance = previous

    @contextmanager
    def session(self, machine: str) -> Iterator[Session]:
        """A committed-on-exit session on a machine's database (with ``Database()`` pointed there)."""
        with self.on(machine) as db, db.get_session() as session:
            yield session

    def client(self, terminal_id: str) -> SyncClient:
        return self.tills[terminal_id][1]

    # --- sync ---

    def push(self, terminal_id: str) -> int:
        with self.on(terminal_id):
            return self.client(terminal_id)._push_transactions()

    def pull(self, terminal_id: str, full: bool = False) -> int:
        with self.on(terminal_id):
            return self.client(terminal_id)._pull_catalog(full_sync=full)

    def cycle(self, terminal_id: str) -> None:
        """One sync cycle, in the order SyncClient.run() does it."""
        with self.on(terminal_id):
            self.client(terminal_id)._sync_cycle()

    def _serve(self, method: str, endpoint: str, data: dict | None) -> dict | None:
        if self.offline:
            return None
        body = sync_json_loads(sync_json_dumps(data)) if data is not None else None
        handler = _Handler(endpoint, body)
        till_db = Database._instance
        Database._instance = self.main
        try:
            if method == "POST" and endpoint == EP_REGISTER:
                handler._handle_register()
            elif method == "POST" and endpoint == EP_PUSH_TRANSACTIONS:
                handler._handle_push_transactions()
            elif method == "GET" and endpoint.startswith(EP_PULL_CATALOG):
                handler._handle_pull_catalog()
            elif method == "GET" and endpoint.startswith(EP_PULL_STOCK):
                handler._handle_pull_stock()
            else:
                raise AssertionError(f"unexpected request {method} {endpoint}")
        finally:
            Database._instance = till_db
        self.last_status = handler.status
        self.last_response = handler.response
        if self.drop_responses or handler.status != 200:
            return None
        return handler.response

    # --- catalog ---

    def seed_catalog(self) -> dict[str, int]:
        """Main PC catalog rows (user + product), then every till pulls them."""
        with self.session("main") as s:
            permission = Permission(code="two_machine_perm")
            role = Role(name="TwoMachineRole", permissions=[permission])
            user = User(username="two_machine_user", pin_hash="x", role=role)
            product = Product(name_en="Two Machine Item", price=Decimal("100"), stock_qty=Decimal("50"), barcode="TM1")
            s.add_all([permission, role, user, product])
            s.flush()
            ids = {"user": user.id, "product": product.id}
        for terminal_id in self.tills:
            assert self.pull(terminal_id, full=True) > 0
        return ids


@contextmanager
def isolated_settings(tmp_dir: str, **values: Any) -> Iterator[None]:
    """Point ConfigService at a throwaway settings file holding ``values``."""
    original_file = ConfigService.SETTINGS_FILE
    original_settings = ConfigService._settings
    ConfigService.SETTINGS_FILE = os.path.join(tmp_dir, "settings.json")
    ConfigService._settings = {}
    ConfigService.load()
    for key, value in values.items():
        ConfigService._settings[key] = value
    try:
        yield
    finally:
        ConfigService.SETTINGS_FILE = original_file
        ConfigService._settings = original_settings
