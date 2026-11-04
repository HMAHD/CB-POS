"""
Integration-style tests for the sync server's request-handling logic.

Exercises the real SyncRequestHandler methods directly (not the HTTP
transport), so regressions in authentication, the transaction-table
whitelist, and stock propagation are caught without needing a live
socket/thread. These three are exactly the gaps a branch review found:
no test previously asserted Product.stock_qty after a synced sale, that
disallowed tables are rejected, or that the shared-secret gate works.
"""

import json
import os
import socket
import time
import urllib.request
from datetime import datetime
from decimal import Decimal

import pytest

from cbpos.core.models import Permission, Product, Role, StockMovement, User
from cbpos.core.services.config_service import ConfigService
from cbpos.core.services.sync_protocol import make_envelope, model_to_dict
from cbpos.infrastructure import sync_tls
from cbpos.infrastructure.sync_server import SyncRequestHandler, SyncServer

_counter = 0


def _next_id() -> int:
    global _counter
    _counter += 1
    return _counter


@pytest.fixture
def test_user(db_session):
    suffix = _next_id()
    permission = Permission(code=f"sync_test_{suffix}")
    role = Role(name=f"SyncRole_{suffix}", permissions=[permission])
    user = User(username=f"sync_user_{suffix}", pin_hash="hash", role=role)
    db_session.add_all([permission, role, user])
    db_session.flush()
    return user


@pytest.fixture
def test_product(db_session):
    suffix = _next_id()
    product = Product(
        name_en=f"SyncProduct_{suffix}",
        price=Decimal("100.00"),
        stock_qty=Decimal("10"),
        barcode=f"SYN{suffix:04d}",
    )
    db_session.add(product)
    db_session.flush()
    return product


class _FakePushHandler:
    """Stand-in for SyncRequestHandler exposing only what
    _handle_push_transactions actually touches."""

    def __init__(self, envelope):
        self._envelope = envelope
        self.response = None
        self.response_status = None

    def _read_json(self):
        return self._envelope

    def _send_json(self, data, status=200):
        self.response = data
        self.response_status = status

    _handle_push_transactions = SyncRequestHandler._handle_push_transactions
    _log_sync = staticmethod(SyncRequestHandler._log_sync)


def _push(envelope):
    handler = _FakePushHandler(envelope)
    handler._handle_push_transactions()
    return handler.response, handler.response_status


class _FakeAuthHandler:
    def __init__(self, headers):
        self.headers = headers


class TestAuthorization:
    """SyncRequestHandler._authorized() — the shared-secret gate."""

    def test_rejects_when_secret_not_configured(self, monkeypatch):
        monkeypatch.setattr(ConfigService, "get", lambda key: "")
        assert SyncRequestHandler._authorized(_FakeAuthHandler({})) is False

    def test_rejects_missing_token(self, monkeypatch):
        monkeypatch.setattr(ConfigService, "get", lambda key: "s3cr3t" if key == "sync_shared_secret" else None)
        assert SyncRequestHandler._authorized(_FakeAuthHandler({})) is False

    def test_rejects_wrong_token(self, monkeypatch):
        monkeypatch.setattr(ConfigService, "get", lambda key: "s3cr3t" if key == "sync_shared_secret" else None)
        handler = _FakeAuthHandler({"X-Sync-Token": "wrong"})
        assert SyncRequestHandler._authorized(handler) is False

    def test_accepts_matching_token(self, monkeypatch):
        monkeypatch.setattr(ConfigService, "get", lambda key: "s3cr3t" if key == "sync_shared_secret" else None)
        handler = _FakeAuthHandler({"X-Sync-Token": "s3cr3t"})
        assert SyncRequestHandler._authorized(handler) is True


class TestPushTableWhitelist:
    """Only TRANSACTION_TABLES may be pushed — catalog/auth tables must be rejected."""

    def test_rejects_disallowed_table(self, db_session):
        terminal_id = f"TERM-TEST-{_next_id()}"
        envelope = make_envelope(
            terminal_id,
            "PUSH_TRANSACTIONS",
            {"users": [{"id": 999999, "username": "hacked", "pin_hash": "x"}]},
            sequence=1,
        )

        response, _status = _push(envelope)

        assert response["records_applied"] == 0
        assert any("not allowed" in e for e in response["errors"])
        assert db_session.query(User).filter_by(username="hacked").first() is None


class TestStockPropagation:
    """A synced StockMovement must update the server's own Product.stock_qty."""

    def _movement(self, movement_id, product_id, user_id, qty_change, balance_after):
        return StockMovement(
            id=movement_id,
            product_id=product_id,
            user_id=user_id,
            timestamp=datetime.now(),
            qty_change=qty_change,
            balance_after=balance_after,
            type="SALE",
            terminal_id="TERM-02",
        )

    def test_new_stock_movement_updates_product_stock(self, db_session, test_user, test_product):
        terminal_id = f"TERM-TEST-{_next_id()}"
        movement = self._movement(_next_id(), test_product.id, test_user.id, Decimal("-3"), Decimal("7"))
        envelope = make_envelope(
            terminal_id,
            "PUSH_TRANSACTIONS",
            {"stock_movements": [model_to_dict(movement)]},
            sequence=1,
        )

        response, _status = _push(envelope)

        assert response["records_applied"] == 1
        db_session.refresh(test_product)
        assert test_product.stock_qty == Decimal("7")

    def test_retried_push_does_not_double_apply(self, db_session, test_user, test_product):
        terminal_id = f"TERM-TEST-{_next_id()}"
        movement_id = _next_id()
        movement = self._movement(movement_id, test_product.id, test_user.id, Decimal("-2"), Decimal("8"))
        envelope = make_envelope(
            terminal_id,
            "PUSH_TRANSACTIONS",
            {"stock_movements": [model_to_dict(movement)]},
            sequence=1,
        )

        _push(envelope)
        db_session.refresh(test_product)
        assert test_product.stock_qty == Decimal("8")

        # Same movement id resent under a NEW sequence number — simulates a
        # terminal that retried after losing the response and incremented
        # its own sequence counter. The registry's sequence-based dedup
        # would not catch this (sequence is higher), so this only stays
        # correct because the movement is found again through sync_id_map
        # and its delta is only applied when that map entry is created.
        retry_envelope = make_envelope(
            terminal_id,
            "PUSH_TRANSACTIONS",
            {"stock_movements": [model_to_dict(movement)]},
            sequence=2,
        )
        _push(retry_envelope)
        db_session.refresh(test_product)
        assert test_product.stock_qty == Decimal("8")


class TestServerResilience:
    """Server-level network concurrency and failure handling."""

    def test_issue_870_idle_tcp_does_not_block_heartbeat(self, tmp_path, monkeypatch):
        # 1. Isolate certs and config
        cert_path = os.path.join(tmp_path, "cert.pem")
        key_path = os.path.join(tmp_path, "key.pem")
        monkeypatch.setattr(sync_tls, "CERT_FILE", cert_path)
        monkeypatch.setattr(sync_tls, "KEY_FILE", key_path)
        sync_tls.get_or_create_certificate()
        with open(cert_path, encoding="ascii") as f:
            cert_pem = f.read()

        monkeypatch.setattr(ConfigService, "get", lambda key: "test-secret" if key == "sync_shared_secret" else None)

        # 2. Pick a free port and start SyncServer
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]

        server = SyncServer(port=port)
        server.start()
        try:
            # Wait until server is listening
            for _ in range(100):
                if server._running and server._server is not None:
                    break
                time.sleep(0.05)
            else:
                pytest.fail("Server did not start in time")

            # 3. Open raw TCP connection and send nothing (idle TCP connection)
            idle_sock = socket.create_connection(("127.0.0.1", port), timeout=2.0)
            try:
                # 4. Make TLS request to /sync/heartbeat with 1s timeout
                client_ctx = sync_tls.build_client_ssl_context(cert_pem)
                req = urllib.request.Request(
                    f"https://127.0.0.1:{port}/sync/heartbeat",
                    headers={"X-Sync-Token": "test-secret"},
                )
                start_time = time.monotonic()
                with urllib.request.urlopen(req, context=client_ctx, timeout=1.0) as resp:
                    elapsed = time.monotonic() - start_time
                    assert resp.status == 200
                    data = json.loads(resp.read().decode("utf-8"))
                    assert data["status"] == "ok"
                    assert elapsed < 1.0
            finally:
                idle_sock.close()
        finally:
            server.stop()
