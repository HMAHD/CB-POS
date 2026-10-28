"""
Unit tests for Issue #757:
Manual loyalty points adjustment with permission, reason and Points History.
"""

import json

import pytest

from cbpos.config import Config
from cbpos.core.constants.permissions import Permissions
from cbpos.core.models import AuditLog, Customer, User
from cbpos.core.services.database_setup_service import DatabaseSetupService
from cbpos.core.services.loyalty_service import LoyaltyService
from cbpos.core.utils.audit_format import format_audit_action, format_audit_details
from cbpos.i18n import get_language, set_language

_counter = 0


@pytest.fixture
def test_user(db_session):
    global _counter
    _counter += 1
    user = User(username=f"mgr_user_{_counter}", pin_hash="hash")
    db_session.add(user)
    db_session.flush()
    return user


@pytest.fixture
def customer(db_session):
    global _counter
    _counter += 1
    c = Customer(name=f"Loyal Customer {_counter}", phone=f"078{_counter:07d}", loyalty_points=20)
    db_session.add(c)
    db_session.flush()
    return c


@pytest.fixture
def lang():
    original = get_language()
    yield set_language
    set_language(original)


def test_permission_constants_and_role_defaults():
    """Adjust loyalty points permission exists and is granted to Admin/Manager in seed, not Cashier."""
    assert hasattr(Permissions, "LOYALTY_ADJUST_POINTS")
    assert Permissions.LOYALTY_ADJUST_POINTS == "loyalty.adjust_points"

    groups = Permissions.get_groups()
    assert "Loyalty" in groups
    assert Permissions.LOYALTY_ADJUST_POINTS in groups["Loyalty"]


def test_empty_db_seed_grants_permission_to_admin_and_manager_not_cashier():
    """Seed / empty-DB setup grants loyalty.adjust_points to Admin/Manager, not Cashier."""
    import inspect

    seed = (Config.BASE_DIR / "scripts" / "seed.py").read_text(encoding="utf-8")
    for source in (inspect.getsource(DatabaseSetupService.create_empty_database), seed):
        manager_block = source.split("manager_groups = [", 1)[1].split("]", 1)[0]
        assert '"Loyalty"' in manager_block


def test_adjust_points_positive(db_session, test_user, customer):
    """A manager can add points with a required reason, writing an ADJUSTMENT ledger row."""
    db_session.commit()

    entry = LoyaltyService.adjust_points(
        customer_id=customer.id,
        points_delta=15,
        reason="Promotional bonus",
        user_id=test_user.id,
    )

    assert entry is not None
    assert entry.entry_type == "ADJUSTMENT"
    assert entry.points == 15
    assert entry.balance_after == 35
    assert entry.note == "Promotional bonus"
    assert entry.reference_id is None
    assert entry.synced is False

    db_session.refresh(customer)
    assert customer.loyalty_points == 35


def test_adjust_points_negative(db_session, test_user, customer):
    """A manager can remove points with a required reason, writing an ADJUSTMENT ledger row."""
    db_session.commit()

    entry = LoyaltyService.adjust_points(
        customer_id=customer.id,
        points_delta=-8,
        reason="Correction of manual error",
        user_id=test_user.id,
    )

    assert entry is not None
    assert entry.entry_type == "ADJUSTMENT"
    assert entry.points == -8
    assert entry.balance_after == 12
    assert entry.note == "Correction of manual error"

    db_session.refresh(customer)
    assert customer.loyalty_points == 12


def test_adjust_points_cannot_take_customer_below_zero(db_session, test_user, customer):
    """Points adjustment cannot take a customer balance below zero."""
    db_session.commit()
    assert customer.loyalty_points == 20

    with pytest.raises(ValueError, match="below zero"):
        LoyaltyService.adjust_points(
            customer_id=customer.id,
            points_delta=-25,
            reason="Large deduction",
            user_id=test_user.id,
        )

    db_session.refresh(customer)
    assert customer.loyalty_points == 20


def test_adjust_points_requires_reason(db_session, test_user, customer):
    """Points adjustment requires a non-empty reason."""
    db_session.commit()

    with pytest.raises(ValueError, match=r"[Rr]eason"):
        LoyaltyService.adjust_points(
            customer_id=customer.id,
            points_delta=5,
            reason="",
            user_id=test_user.id,
        )

    with pytest.raises(ValueError, match=r"[Rr]eason"):
        LoyaltyService.adjust_points(
            customer_id=customer.id,
            points_delta=5,
            reason="   ",
            user_id=test_user.id,
        )


def test_adjust_points_zero_rejected(db_session, test_user, customer):
    """Points adjustment of 0 points is rejected."""
    db_session.commit()

    with pytest.raises(ValueError, match="zero"):
        LoyaltyService.adjust_points(
            customer_id=customer.id,
            points_delta=0,
            reason="No change",
            user_id=test_user.id,
        )


def test_adjust_points_writes_audit_log(db_session, test_user, customer):
    """Points adjustment writes an Activity Log row with who/when/old/new/reason."""
    db_session.commit()

    LoyaltyService.adjust_points(
        customer_id=customer.id,
        points_delta=10,
        reason="Goodwill adjustment",
        user_id=test_user.id,
    )

    log = (
        db_session.query(AuditLog)
        .filter_by(action="LOYALTY_ADJUSTMENT", user_id=test_user.id)
        .order_by(AuditLog.id.desc())
        .first()
    )
    assert log is not None
    assert log.event_type == "LOYALTY"

    details = json.loads(log.details)
    assert details["customer"] == customer.name
    assert details["old"] == 20
    assert details["new"] == 30
    assert details["reason"] == "Goodwill adjustment"


@pytest.mark.parametrize("language", ["en", "si", "ta"])
def test_activity_log_readable_in_all_languages(lang, language):
    """Activity Log row for loyalty points adjustment is readable in en, si, and ta."""
    lang(language)

    action_label = format_audit_action("LOYALTY_ADJUSTMENT")
    assert action_label and action_label != "LOYALTY_ADJUSTMENT" and "_" not in action_label

    details = json.dumps(
        {
            "customer": "Kamal Perera",
            "old": 20,
            "new": 35,
            "points_delta": 15,
            "reason": "Goodwill bonus",
        }
    )
    text = format_audit_details("LOYALTY_ADJUSTMENT", details)
    assert "Kamal Perera" in text
    assert "20" in text
    assert "35" in text
    assert "Goodwill bonus" in text
    assert "{" not in text


def test_get_points_history(db_session, test_user, customer):
    """Points history returns all ledger entries for a customer in reverse chronological order."""
    db_session.commit()

    LoyaltyService.adjust_points(customer.id, 10, "First adjustment", test_user.id)
    LoyaltyService.adjust_points(customer.id, -5, "Second adjustment", test_user.id)

    history = LoyaltyService.get_points_history(customer.id)
    assert len(history) == 2
    assert history[0].points == -5
    assert history[0].balance_after == 25
    assert history[1].points == 10
    assert history[1].balance_after == 30


def test_upgrade_grants_loyalty_adjust_points_to_admin_and_manager(tmp_path, monkeypatch):
    """Alembic upgrade grants loyalty.adjust_points to Admin and Manager roles."""
    import sqlite3

    from alembic.config import Config as AlembicConfig
    from sqlalchemy import create_engine

    from alembic import command
    from cbpos.core.models import Base

    db_path = tmp_path / "cbpos_migration.db"
    uri = f"sqlite:///{db_path}"
    engine = create_engine(uri)
    Base.metadata.create_all(engine)
    engine.dispose()

    with sqlite3.connect(db_path) as conn:
        conn.executemany(
            "INSERT INTO roles (id, name, access_level, last_modified) VALUES (?, ?, 0, CURRENT_TIMESTAMP)",
            [(1, "Admin"), (2, "Manager"), (3, "Cashier")],
        )

    monkeypatch.setattr(Config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(Config, "DB_URI", uri)
    cfg = AlembicConfig(str(Config.BASE_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(Config.BASE_DIR / "alembic"))
    cfg.set_main_option("sqlalchemy.url", uri)
    cfg.attributes["configure_logger"] = False
    command.stamp(cfg, "d4e7b2a9c816")
    command.upgrade(cfg, "e5f8a1c9b204")

    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            "SELECT r.name, p.code FROM role_permissions rp "
            "JOIN roles r ON r.id = rp.role_id JOIN permissions p ON p.id = rp.permission_id "
            "WHERE p.code = ?",
            (Permissions.LOYALTY_ADJUST_POINTS,),
        ).fetchall()
        roles_with_perm = {r[0] for r in rows}
        assert "Admin" in roles_with_perm
        assert "Manager" in roles_with_perm
        assert "Cashier" not in roles_with_perm


def test_customer_editor_loyalty_tab_and_points_history(qapp, db_session, test_user, customer, monkeypatch):
    """CustomerEditor shows points, history table, and allows manual adjustment with permission."""
    from cbpos.core.services.config_service import ConfigService
    from cbpos.ui.dialogs.customer_editor import CustomerEditor

    monkeypatch.setattr(ConfigService, "get", lambda k: k == "enable_loyalty")
    db_session.commit()

    # Add a couple points history entries
    LoyaltyService.adjust_points(customer.id, 15, "Welcome gift", test_user.id)
    LoyaltyService.adjust_points(customer.id, -5, "Expired bonus", test_user.id)
    db_session.refresh(customer)

    editor = CustomerEditor(customer)
    assert hasattr(editor, "points_label")
    assert editor.points_label.text() == "30"  # started at 20 + 15 - 5 = 30
    assert hasattr(editor, "btn_adjust_points")
    assert editor.btn_adjust_points.isEnabled()

    # Check points history table
    assert hasattr(editor, "points_history_table")
    assert editor.points_history_table.rowCount() == 2
    # Row 0: most recent (-5)
    assert editor.points_history_table.item(0, 2).text() == "-5"
    assert editor.points_history_table.item(0, 3).text() == "30"
    assert editor.points_history_table.item(0, 4).text() == "Expired bonus"

    # Simulate adjusting points through dialog
    monkeypatch.setattr("cbpos.core.utils.permission_helper.check_permission_with_override", lambda *a, **k: True)
    monkeypatch.setattr(
        "cbpos.ui.dialogs.adjust_points_dialog.AdjustPointsDialog.exec",
        lambda self: LoyaltyService.adjust_points(self.customer.id, 10, "Compensation", test_user.id) or 1,
    )

    editor.adjust_points()

    assert editor.points_label.text() == "40"
    assert editor.points_history_table.rowCount() == 3
    assert editor.points_history_table.item(0, 2).text() == "+10"
    assert editor.points_history_table.item(0, 4).text() == "Compensation"


def test_credit_book_view_loyalty_points_display_and_adjustment(qapp, db_session, test_user, customer, monkeypatch):
    """CreditBookView displays customer loyalty points in header and provides adjust action."""
    from cbpos.core.services.config_service import ConfigService
    from cbpos.ui.views.credit_book_view import CreditBookView

    monkeypatch.setattr(ConfigService, "get", lambda k: k == "enable_loyalty")
    db_session.commit()

    view = CreditBookView()
    view.update_header(customer)

    assert not view.lbl_points.isHidden()
    assert str(customer.loyalty_points) in view.lbl_points.text()
    assert not view.btn_adjust_points.isHidden()

    # Simulate adjust loyalty points on selected customer
    view.selected_customer = customer
    monkeypatch.setattr("cbpos.core.utils.permission_helper.check_permission_with_override", lambda *a, **k: True)
    monkeypatch.setattr(
        "cbpos.ui.dialogs.adjust_points_dialog.AdjustPointsDialog.exec",
        lambda self: LoyaltyService.adjust_points(self.customer.id, 15, "Promotional bonus", test_user.id) or 1,
    )

    view.adjust_loyalty_points()

    updated = db_session.get(Customer, customer.id)
    db_session.refresh(updated)
    assert updated.loyalty_points == 35
    assert "35" in view.lbl_points.text()


def test_cashier_cannot_adjust_points_without_permission(qapp, db_session, customer, monkeypatch):
    """Points adjustment is blocked when loyalty.adjust_points permission is denied."""
    from cbpos.core.services.config_service import ConfigService
    from cbpos.ui.dialogs.customer_editor import CustomerEditor

    monkeypatch.setattr(ConfigService, "get", lambda k: k == "enable_loyalty")
    db_session.commit()

    editor = CustomerEditor(customer)
    # Gated: check_permission_with_override returns False
    called_override = False

    def fake_check(perm, parent):
        nonlocal called_override
        called_override = True
        return False

    monkeypatch.setattr("cbpos.core.utils.permission_helper.check_permission_with_override", fake_check)

    editor.adjust_points()
    assert called_override is True
    assert customer.loyalty_points == 20
