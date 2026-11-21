from decimal import Decimal
from unittest.mock import patch

import pytest

from cbpos.core.constants.features import Features
from cbpos.core.constants.permissions import Permissions
from cbpos.core.models import Permission, Product, Purchase, Role, Supplier, Unit, User
from cbpos.core.services.feature_flags import FeatureFlags
from cbpos.ui.dialogs.product_editor import ProductEditor
from cbpos.ui.views.purchase_view import PurchaseView

pytestmark = pytest.mark.usefixtures("qapp")

_counter = 0


@pytest.fixture
def units(db_session):
    piece = Unit(name="Piece", abbreviation="pcs", decimal_places=0)
    box = Unit(name="Box", abbreviation="box", decimal_places=0)
    db_session.add_all([piece, box])
    db_session.flush()
    return {"piece": piece, "box": box}


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
    role = Role(name=f"UnitConvUI_{_counter}", permissions=[p_grn, p_inv])
    user = User(username=f"conv_ui_user_{_counter}", pin_hash="hash", role=role)
    db_session.add_all([role, user])
    db_session.flush()
    return user


@pytest.fixture
def test_supplier(db_session):
    global _counter
    _counter += 1
    supplier = Supplier(company_name=f"UI Test Supplier {_counter}", current_payable=Decimal("0.00"))
    db_session.add(supplier)
    db_session.flush()
    return supplier


def test_product_editor_shows_conversion_only_when_feature_on(db_session, units):
    """ProductEditor shows purchase unit combo, factor, and helper label only when feature is on."""
    # When feature is off:
    with patch.object(FeatureFlags, "is_on", return_value=False):
        editor_off = ProductEditor()
        # Purchase unit controls should either not exist or be hidden
        assert not hasattr(editor_off, "purchase_unit_combo") or editor_off.purchase_unit_combo.isHidden()

    # When feature is on:
    with patch.object(FeatureFlags, "is_on", return_value=True):
        editor_on = ProductEditor()
        assert hasattr(editor_on, "purchase_unit_combo")
        assert hasattr(editor_on, "purchase_factor_input")
        assert not editor_on.purchase_unit_combo.isHidden()
        assert not editor_on.purchase_factor_input.isHidden()


def test_purchase_view_grid_columns_adapt_to_feature_flag(db_session, test_user, test_supplier, units):
    """When UNIT_CONVERSION is off, GRN grid has 5 columns; when on, has purchase/base unit columns."""
    # Feature OFF: standard 5 columns
    with patch.object(FeatureFlags, "is_on", return_value=False):
        view_off = PurchaseView()
        assert view_off.grn_model.columnCount() == 5

    # Feature ON: expanded columns showing purchase qty, purchase unit, base qty, purchase cost, total
    with patch.object(FeatureFlags, "is_on", return_value=True):
        view_on = PurchaseView()
        assert view_on.grn_model.columnCount() >= 6


def test_purchase_view_editing_purchase_qty_updates_base_qty_and_total(db_session, test_user, test_supplier, units):
    """In PurchaseView with UNIT_CONVERSION on, editing purchase qty dynamically updates base qty and total."""
    product = Product(
        name_en="Antibiotic Strips",
        barcode="MEDSTRIP01",
        price=Decimal("20.00"),
        cost=Decimal("10.00"),
        stock_qty=Decimal("0"),
        unit_id=units["piece"].id,
        purchase_unit_id=units["box"].id,
        purchase_factor=Decimal("10.000"),
    )
    db_session.add(product)
    db_session.flush()

    with patch.object(FeatureFlags, "is_on", return_value=True):
        view = PurchaseView()
        view.set_user(test_user)
        view._add_grn_row(product, Decimal("2"), Decimal("100.00"))

        # Row 0: 2 boxes @ 100.00 -> 20 pieces base qty, line total 200.00
        # Check base qty cell contains 20
        base_qty_text = view.grn_model.item(0, 4).text()
        assert "20" in base_qty_text

        # Total cost label contains 200.00
        view.update_total()
        assert "200.00" in view.total_label.text()


def test_grn_detail_dialog_displays_both_units_historically(db_session, test_user, test_supplier, units):
    """GRNDetailDialog displays immutable purchase facts and both unit quantities."""
    from datetime import datetime

    from cbpos.core.services.purchase_service import GrnLine, GrnRequest, PurchaseService
    from cbpos.ui.dialogs.grn_detail_dialog import GRNDetailDialog

    product = Product(
        name_en="Antibiotic Strips Hist",
        barcode="MEDHIST01",
        price=Decimal("20.00"),
        cost=Decimal("10.00"),
        stock_qty=Decimal("0"),
        unit_id=units["piece"].id,
        purchase_unit_id=units["box"].id,
        purchase_factor=Decimal("10.000"),
    )
    db_session.add(product)
    db_session.flush()

    with patch.object(FeatureFlags, "is_on", return_value=True):
        req = GrnRequest(
            supplier_id=test_supplier.id,
            date_received=datetime.now(),
            supplier_invoice_no="INV-HIST-DLG",
            input_vat=Decimal("0.00"),
            lines=[
                GrnLine(
                    product_id=product.id,
                    qty=Decimal("2.000"),
                    unit_cost=Decimal("100.00"),
                    purchase_unit_id=units["box"].id,
                    purchase_factor=Decimal("10.000"),
                )
            ],
            user_id=test_user.id,
        )

        purchase = PurchaseService.receive_goods(req)

        # Later: product factor modified on catalog
        product.purchase_factor = Decimal("15.000")
        db_session.commit()

        dialog = GRNDetailDialog(purchase.id)
        # Check that row 0 displays 2 Box (20 Piece)
        qty_item = dialog.table.item(0, 2)
        assert "2" in qty_item.text()
        assert "Box" in qty_item.text()
        assert "20" in qty_item.text()
        assert "Piece" in qty_item.text()


def test_grn_numeric_delegate_validates_cost_on_col_5(db_session, test_user, test_supplier, units):
    """GrnNumericDelegate validates column 5 in 7-column mode, rejecting negative numbers."""

    with patch.object(FeatureFlags, "is_on", return_value=True):
        view = PurchaseView()
        delegate = view.grn_numeric_delegate

        # Create dummy product in grid
        product = Product(
            name_en="Item For Delegate",
            barcode="ITEMDEL01",
            price=Decimal("10.00"),
            cost=Decimal("5.00"),
            stock_qty=Decimal("0"),
            unit_id=units["piece"].id,
            purchase_unit_id=units["box"].id,
            purchase_factor=Decimal("10.000"),
        )
        db_session.add(product)
        db_session.flush()

        view._add_grn_row(product, Decimal("1.000"), Decimal("50.00"))
        # In 7-column mode, col 5 is Purchase Cost
        model_idx_5 = view.grn_model.index(0, 5)

        editor = delegate.createEditor(view, None, model_idx_5)
        assert editor.validator() is not None

        # Attempt to set negative cost
        editor.setText("-25.00")
        delegate.setModelData(editor, view.grn_model, model_idx_5)
        # Value must NOT have changed to negative
        assert view.grn_model.data(model_idx_5) == "50.00"

        # Valid positive cost
        editor.setText("75.50")
        delegate.setModelData(editor, view.grn_model, model_idx_5)
        assert view.grn_model.data(model_idx_5) == "75.50"


def test_prefill_grn_items_converts_base_order_qty_to_purchase_units(db_session, test_user, units):
    """prefill_grn_items converts base order quantity to purchase units when conversion is active."""
    product = Product(
        name_en="Bulk Solder Wire",
        barcode="SOLDER001",
        price=Decimal("50.00"),
        cost=Decimal("20.00"),  # 20.00 per meter
        stock_qty=Decimal("5.000"),
        unit_id=units["piece"].id,  # e.g. Meter
        purchase_unit_id=units["box"].id,  # Roll of 10m
        purchase_factor=Decimal("10.000"),
    )
    db_session.add(product)
    db_session.flush()

    with patch.object(FeatureFlags, "is_on", return_value=True):
        view = PurchaseView()
        # Reorder orders 20 meters (base units)
        view.prefill_grn_items([{"barcode": "SOLDER001", "order_qty": Decimal("20.000")}])

        assert view.grn_model.rowCount() == 1
        # Purchase Qty should be 20 / 10 = 2 rolls
        assert view.grn_model.data(view.grn_model.index(0, 2)) == "2.000"
        # Base Qty should show 20
        assert "20" in view.grn_model.data(view.grn_model.index(0, 4))
        # Purchase Cost should be 20.00 * 10 = 200.00
        assert view.grn_model.data(view.grn_model.index(0, 5)) == "200.00"


def test_product_editor_preserves_inactive_purchase_unit(db_session, units):
    """ProductEditor must preserve inactive purchase_unit_id and display (inactive)."""
    product = Product(
        name_en="Special Tape",
        barcode="TAPE001",
        price=Decimal("10.00"),
        cost=Decimal("4.00"),
        stock_qty=Decimal("0.000"),
        unit_id=units["piece"].id,
        purchase_unit_id=units["box"].id,
        purchase_factor=Decimal("6.000"),
    )
    db_session.add(product)
    db_session.flush()

    # Deactivate the box unit
    units["box"].is_active = False
    db_session.commit()

    with patch.object(FeatureFlags, "is_on", return_value=True):
        editor = ProductEditor(product)
        idx = editor.purchase_unit_combo.findData(units["box"].id)
        assert idx >= 0
        assert "(inactive)" in editor.purchase_unit_combo.itemText(idx).lower()


def test_issue_937_purchase_view_handles_bare_mock_product(qtbot, db_session):
    """PurchaseView must safely handle bare MagicMock products without raising TypeError (#937)."""
    from unittest.mock import MagicMock

    with patch.object(FeatureFlags, "is_on", return_value=True):
        view = PurchaseView()
        qtbot.addWidget(view)
        mock_prod = MagicMock(id=999, name_en="Bare Mock Product", cost=Decimal("15.00"))
        view._add_grn_row(product=mock_prod, qty=Decimal("3"), cost=Decimal("15.00"))
        assert view.grn_model.rowCount() == 1


def test_issue_937_purchase_view_refreshes_empty_grid_on_feature_toggle(qtbot, db_session):
    """PurchaseView must immediately rebuild empty GRN grid when UNIT_CONVERSION changes (#937)."""
    flag_state = {"enabled": False}

    with patch.object(
        FeatureFlags,
        "is_on",
        side_effect=lambda name: flag_state["enabled"] if name == Features.UNIT_CONVERSION else False,
    ):
        view = PurchaseView()
        qtbot.addWidget(view)

        # Initially 5 columns
        assert view.grn_model.columnCount() == 5
        assert not view._is_unit_conv

        # Feature enabled
        flag_state["enabled"] = True
        view.on_activated()

        # Rebuilt to 7 columns
        assert view.grn_model.columnCount() == 7
        assert view._is_unit_conv

        # Feature disabled again
        flag_state["enabled"] = False
        view.on_activated()

        # Rebuilt back to 5 columns
        assert view.grn_model.columnCount() == 5
        assert not view._is_unit_conv


def test_issue_937_purchase_view_populated_grid_prompts_on_feature_toggle_cancel_and_confirm(
    qtbot, db_session, test_user, test_supplier, units, monkeypatch
):
    """Populated GRN grid must prompt before rebuilding on feature toggle, with safe cancel and confirm (#937)."""
    from PyQt6.QtWidgets import QMessageBox

    flag_state = {"enabled": True}

    product = Product(
        name_en="Toggle Test Item",
        barcode="TOGGLE001",
        price=Decimal("25.00"),
        cost=Decimal("10.00"),
        stock_qty=Decimal("0.000"),
        unit_id=units["piece"].id,
        purchase_unit_id=units["box"].id,
        purchase_factor=Decimal("5.000"),
    )
    db_session.add(product)
    db_session.commit()

    with patch.object(
        FeatureFlags,
        "is_on",
        side_effect=lambda name: flag_state["enabled"] if name == Features.UNIT_CONVERSION else False,
    ):
        view = PurchaseView()
        view.set_user(test_user)
        qtbot.addWidget(view)

        assert view.grn_model.columnCount() == 7
        assert view._is_unit_conv

        # Add a row
        view._add_grn_row(product, Decimal("2.000"), Decimal("50.00"), mode="PURCHASE")
        assert view.grn_model.rowCount() == 1

        # Toggle feature OFF while row is open
        flag_state["enabled"] = False

        # 1. User cancels reload prompt: rows preserved, flag state preserved
        prompt_called = {"count": 0}

        def mock_question_no(*args, **kwargs):
            prompt_called["count"] += 1
            return QMessageBox.StandardButton.No

        monkeypatch.setattr(QMessageBox, "question", mock_question_no)
        view.on_activated()

        assert prompt_called["count"] == 1
        assert view.grn_model.rowCount() == 1
        assert view.grn_model.columnCount() == 7
        assert view._is_unit_conv is True  # preserved

        # 2. User confirms reload prompt: rows cleared, grid rebuilt to 5 cols
        def mock_question_yes(*args, **kwargs):
            prompt_called["count"] += 1
            return QMessageBox.StandardButton.Yes

        monkeypatch.setattr(QMessageBox, "question", mock_question_yes)
        view.on_activated()

        assert prompt_called["count"] == 2
        assert view.grn_model.rowCount() == 0
        assert view.grn_model.columnCount() == 5
        assert view._is_unit_conv is False

        # 3. New GRN commits cleanly without restart
        view.supplier_combo.setCurrentIndex(view.supplier_combo.findData(test_supplier.id))
        view.invoice_input.setText("INV-AFTER-RELOAD")
        view._add_grn_row(product, Decimal("4.000"), Decimal("10.00"), mode="BASE")
        assert view.grn_model.rowCount() == 1

        monkeypatch.setattr(QMessageBox, "information", lambda *args, **kwargs: None)
        view.commit_grn()

        # Successfully committed
        assert view.grn_model.rowCount() == 0
        purchase = db_session.query(Purchase).filter_by(reference_external="INV-AFTER-RELOAD").first()
        assert purchase is not None
        assert purchase.status == "COMPLETED"
