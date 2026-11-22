from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QMessageBox

from cbpos.core.constants.features import Features
from cbpos.core.constants.permissions import Permissions
from cbpos.core.models import Permission, Product, ProductBatch, Role, Supplier, User
from cbpos.ui.dialogs.batch_picker import BatchPickerModal
from cbpos.ui.dialogs.expiring_batches_dialog import ExpiringBatchesDialog
from cbpos.ui.dialogs.product_editor import ProductEditor
from cbpos.ui.dialogs.stock_adjustment_dialog import StockAdjustmentDialog
from cbpos.ui.views.dashboard_view import DashboardView
from cbpos.ui.views.purchase_view import PurchaseView

pytestmark = pytest.mark.usefixtures("qapp")

_counter = 0


@pytest.fixture
def test_user(db_session):
    global _counter
    _counter += 1
    p_grn = db_session.query(Permission).filter_by(code=Permissions.PURCHASE_CREATE_GRN).first()
    if not p_grn:
        p_grn = Permission(code=Permissions.PURCHASE_CREATE_GRN, description="Create GRN", group="Purchase")
        db_session.add(p_grn)
    p_inv = db_session.query(Permission).filter_by(code=Permissions.INVENTORY_EDIT).first()
    if not p_inv:
        p_inv = Permission(code=Permissions.INVENTORY_EDIT, description="Edit inventory", group="Inventory")
        db_session.add(p_inv)
    p_adj = db_session.query(Permission).filter_by(code=Permissions.INVENTORY_STOCK_ADJUST).first()
    if not p_adj:
        p_adj = Permission(code=Permissions.INVENTORY_STOCK_ADJUST, description="Adjust stock", group="Inventory")
        db_session.add(p_adj)
    p_override = db_session.query(Permission).filter_by(code=Permissions.SALES_OVERRIDE_EXPIRED_BATCH).first()
    if not p_override:
        p_override = Permission(
            code=Permissions.SALES_OVERRIDE_EXPIRED_BATCH, description="Override expired batch", group="Sales"
        )
        db_session.add(p_override)
    role = Role(name=f"BatchUI_{_counter}", permissions=[p_grn, p_inv, p_adj, p_override])
    user = User(username=f"batch_ui_user_{_counter}", pin_hash="hash", role=role)
    db_session.add_all([role, user])
    db_session.flush()
    return user


@pytest.fixture
def test_supplier(db_session):
    global _counter
    _counter += 1
    supplier = Supplier(company_name=f"Batch UI Supplier {_counter}", current_payable=Decimal("0.00"))
    db_session.add(supplier)
    db_session.flush()
    return supplier


def test_issue_926_batch_picker_dialog_keyboard_selection(qtbot, db_session):
    """BatchPickerModal displays candidate batches, allows Up/Down arrow navigation, and Enter to select."""
    prod = Product(
        name_en="Batch Biscuit",
        barcode="BAR-BATCH-PKR",
        price=Decimal("100.00"),
        stock_qty=Decimal("20.000"),
        tracks_batches=True,
    )
    db_session.add(prod)
    db_session.flush()

    b1 = ProductBatch(
        product_id=prod.id,
        batch_no="B001",
        expiry_date=date(2027, 6, 30),
        mrp=Decimal("100.00"),
        cost=Decimal("70.00"),
        qty_on_hand=Decimal("10.000"),
        is_active=True,
    )
    b2 = ProductBatch(
        product_id=prod.id,
        batch_no="B002",
        expiry_date=date(2027, 8, 31),
        mrp=Decimal("120.00"),
        cost=Decimal("80.00"),
        qty_on_hand=Decimal("10.000"),
        is_active=True,
    )
    db_session.add_all([b1, b2])
    db_session.commit()

    dialog = BatchPickerModal(prod)
    qtbot.addWidget(dialog)

    assert dialog.tbl_batches.rowCount() == 2
    # First row is initially selected
    assert dialog.tbl_batches.currentRow() == 0

    # Key Down moves to second row
    qtbot.keyClick(dialog.tbl_batches, Qt.Key.Key_Down)
    assert dialog.tbl_batches.currentRow() == 1

    # Key Enter accepts dialog
    with qtbot.waitSignal(dialog.accepted, timeout=1000):
        qtbot.keyClick(dialog, Qt.Key.Key_Return)

    selected = dialog.get_selected_batch()
    assert selected is not None
    assert selected.id == b2.id
    assert selected.batch_no == "B002"


def test_issue_926_grn_batch_expiry_inline_inputs(qtbot, db_session, test_user, test_supplier):
    """PurchaseView GRN table includes batch columns and validates MM/YY expiry."""
    prod = Product(
        name_en="Batch Paracetamol",
        barcode="BAR-PARA-GRN",
        price=Decimal("50.00"),
        stock_qty=Decimal("0.000"),
        tracks_batches=True,
    )
    db_session.add(prod)
    db_session.commit()

    with (
        patch("cbpos.ui.views.purchase_view.feature_visible") as mock_feat,
        patch("cbpos.ui.views.purchase_view.check_permission_with_override", return_value=test_user),
    ):
        mock_feat.side_effect = lambda feat: feat in (Features.BATCHES, Features.EXPIRY_DATES)
        view = PurchaseView()
        qtbot.addWidget(view)
        view.set_user(test_user)

        # 8 columns (id, name, qty, cost, batch_no, expiry, mrp, total)
        assert view.grn_model.columnCount() == 8

        view.supplier_combo.addItem(test_supplier.company_name, test_supplier.id)
        view.supplier_combo.setCurrentIndex(0)
        view.invoice_input.setText("INV-BATCH-001")

        view._add_grn_row(prod, Decimal("1.000"), Decimal("30.00"))
        assert view.grn_model.rowCount() == 1

        # 1. Invalid expiry format test
        view.grn_model.item(0, 5).setText("invalid_date")
        with patch.object(QMessageBox, "warning") as mock_warn:
            view.commit_grn()
            assert mock_warn.called
            # Product stock shouldn't have changed
            p = db_session.get(Product, prod.id)
            assert p.stock_qty == Decimal("0.000")

        # 2. Missing batch/expiry for tracked product test
        view.grn_model.item(0, 4).setText("")
        view.grn_model.item(0, 5).setText("")
        with patch.object(QMessageBox, "warning") as mock_warn:
            view.commit_grn()
            assert mock_warn.called

        # 3. Valid batch and expiry commit test
        view.grn_model.item(0, 2).setText("15")  # qty
        view.grn_model.item(0, 3).setText("30.00")  # cost
        view.grn_model.item(0, 4).setText("LOT-999")  # batch_no
        view.grn_model.item(0, 5).setText("10/28")  # expiry MM/YY -> 2028-10-31
        view.grn_model.item(0, 6).setText("55.00")  # mrp

        with (
            patch.object(QMessageBox, "information") as mock_info,
            patch.object(QMessageBox, "critical") as mock_crit,
        ):
            view.commit_grn()
            assert not mock_crit.called
            assert mock_info.called

        p = db_session.get(Product, prod.id)
        assert p.stock_qty == Decimal("15.000")

        batches = db_session.query(ProductBatch).filter_by(product_id=prod.id).all()
        assert len(batches) == 1
        assert batches[0].batch_no == "LOT-999"
        assert batches[0].expiry_date == date(2028, 10, 31)
        assert batches[0].mrp == Decimal("55.00")
        assert batches[0].qty_on_hand == Decimal("15.000")


def test_issue_926_stock_adjustment_dialog_with_batch(qtbot, db_session, test_user):
    """StockAdjustmentDialog allows selecting a batch and recording adjustment with batch_id."""
    prod = Product(
        name_en="Tracked Tea",
        barcode="BAR-TEA-ADJ",
        price=Decimal("200.00"),
        stock_qty=Decimal("15.000"),
        tracks_batches=True,
    )
    db_session.add(prod)
    db_session.flush()

    b1 = ProductBatch(
        product_id=prod.id,
        batch_no="TEA-01",
        expiry_date=date(2027, 5, 31),
        mrp=Decimal("200.00"),
        cost=Decimal("140.00"),
        qty_on_hand=Decimal("15.000"),
        is_active=True,
    )
    db_session.add(b1)
    db_session.commit()

    dialog = StockAdjustmentDialog(prod, default_reason="EXPIRED")
    qtbot.addWidget(dialog)

    # Batch combo should be visible and populated
    assert hasattr(dialog, "cmb_batch")
    assert dialog.cmb_batch is not None
    assert not dialog.cmb_batch.isHidden()
    assert dialog.cmb_batch.count() == 2  # "All / Unspecified" + 1 batch
    dialog.cmb_batch.setCurrentIndex(1)
    assert dialog.cmb_batch.currentData() == b1.id

    dialog.qty_spin.setValue(5.0)
    dialog.radio_remove.setChecked(True)

    with (
        patch.object(dialog.inventory_service, "adjust_stock") as mock_adjust,
        patch("cbpos.ui.dialogs.stock_adjustment_dialog.check_permission_with_override", return_value=test_user),
        patch.object(QMessageBox, "information"),
    ):
        dialog.save_adjustment()
        mock_adjust.assert_called_once()
        _, kwargs = mock_adjust.call_args
        assert kwargs.get("batch_id") == b1.id
        assert kwargs.get("qty_change") == Decimal("-5")
        assert kwargs.get("reason") == "EXPIRED"


def test_issue_926_product_editor_tracks_batches(qtbot, db_session):
    """ProductEditor provides a tracks_batches checkbox disabled for composite products."""
    with patch("cbpos.core.services.feature_flags.feature_visible", return_value=True):
        # 1. Standard product
        editor = ProductEditor()
        qtbot.addWidget(editor)
        assert hasattr(editor, "chk_tracks_batches")
        assert editor.chk_tracks_batches is not None
        assert editor.chk_tracks_batches.isEnabled()

        # 2. Composite components disable batch tracking
        editor.comp_table.setRowCount(1)
        editor._update_batch_tracking_enabled()
        assert not editor.chk_tracks_batches.isEnabled()
        assert not editor.chk_tracks_batches.isChecked()


def test_issue_926_dashboard_expiring_batches_actions(qtbot, db_session):
    """ExpiringBatchesDialog displays filtered batches, handles write-off, and disables supplier returns."""
    prod = Product(
        name_en="Expiring Cream",
        barcode="BAR-CREAM-99",
        price=Decimal("250.00"),
        stock_qty=Decimal("10.000"),
        tracks_batches=True,
    )
    db_session.add(prod)
    db_session.flush()

    today = date.today()
    b = ProductBatch(
        product_id=prod.id,
        batch_no="CR-01",
        expiry_date=today + timedelta(days=10),
        mrp=Decimal("250.00"),
        cost=Decimal("180.00"),
        qty_on_hand=Decimal("10.000"),
        is_active=True,
    )
    db_session.add(b)
    db_session.commit()

    dialog = ExpiringBatchesDialog()
    qtbot.addWidget(dialog)

    assert dialog.table.rowCount() == 1
    assert dialog.btn_write_off.isEnabled()
    # Supplier return button is disabled with informational tooltip (#930)
    assert not dialog.btn_supplier_return.isEnabled()
    assert "#930" in dialog.btn_supplier_return.toolTip()

    # Test write-off launches StockAdjustmentDialog
    with (
        patch("cbpos.ui.dialogs.expiring_batches_dialog.StockAdjustmentDialog") as mock_adj_cls,
    ):
        mock_instance = MagicMock()
        mock_instance.exec.return_value = False
        mock_adj_cls.return_value = mock_instance

        dialog.btn_write_off.click()
        mock_adj_cls.assert_called_once()
        _, kwargs = mock_adj_cls.call_args
        assert kwargs.get("batch_id") == b.id
        assert kwargs.get("default_reason") == "EXPIRED"


def test_issue_926_dashboard_expiring_tile_integration(qtbot, db_session):
    """DashboardView displays Expiring Soon tile and loads counts via background worker."""
    with patch("cbpos.core.services.feature_flags.feature_visible", return_value=True):
        view = DashboardView()
        qtbot.addWidget(view)

        assert hasattr(view, "expiring_batches_panel")
        assert not view.expiring_batches_panel.isHidden()

        # Simulate worker data ready
        view._on_expiring_batches_tile_ready({"expiring_30": 4, "expired": 2})
        assert view.lbl_expiring_soon_val.text() == "4"
        assert view.lbl_expired_val.text() == "2"
