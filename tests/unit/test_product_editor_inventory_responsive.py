import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QFrame, QSizePolicy

from cbpos.ui.dialogs.product_editor import ProductEditor

pytestmark = pytest.mark.usefixtures("qapp")


def test_inventory_tab_scroll_area_wrapper(db_session):
    dlg = ProductEditor()
    try:
        assert hasattr(dlg, "inventory_scroll")
        assert dlg.inventory_scroll.widgetResizable()
        assert dlg.inventory_scroll.frameShape() == QFrame.Shape.NoFrame
        assert dlg.inventory_scroll.horizontalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        assert dlg.inventory_scroll.widget() is not None
        assert dlg.inventory_scroll.widget().objectName() == "InventoryScrollInner"
    finally:
        dlg.deleteLater()


def test_inventory_tab_inputs_and_checkboxes_size_policies(db_session):
    dlg = ProductEditor()
    try:
        # Inputs must have Fixed vertical size policy to prevent vertical squashing
        for inp in [dlg.stock_input, dlg.reorder_input, dlg.preferred_qty_input]:
            assert inp.sizePolicy().verticalPolicy() == QSizePolicy.Policy.Fixed
            assert inp.sizePolicy().horizontalPolicy() == QSizePolicy.Policy.Expanding

        for combo in [dlg.supplier_combo, dlg.unit_combo]:
            assert combo.sizePolicy().verticalPolicy() == QSizePolicy.Policy.Fixed
            assert combo.sizePolicy().horizontalPolicy() == QSizePolicy.Policy.Expanding

        # Checkboxes must have Maximum horizontal and Minimum vertical policy to prevent indicator clipping
        for chk in [
            dlg.weighted_check,
            dlg.service_check,
            dlg.price_change_allowed_check,
            dlg.age_restricted_check,
        ]:
            assert chk.sizePolicy().horizontalPolicy() == QSizePolicy.Policy.Maximum
            assert chk.sizePolicy().verticalPolicy() == QSizePolicy.Policy.Minimum
    finally:
        dlg.deleteLater()


def test_inventory_stock_section_3_column_row(db_session):
    dlg = ProductEditor()
    try:
        # Stock group must hold stock, reorder, and preferred qty in a 3-column row
        parent_box = dlg.stock_input.parentWidget()
        assert dlg.reorder_input.parentWidget() == parent_box
        assert dlg.preferred_qty_input.parentWidget() == parent_box

        # Layout of the stock group box is horizontal
        stock_layout = parent_box.layout()
        assert stock_layout.count() == 3
        for i in range(3):
            item = stock_layout.itemAt(i)
            # Each item is a column QVBoxLayout with a label and input
            col_layout = item.layout()
            assert col_layout is not None
            assert col_layout.count() == 2
    finally:
        dlg.deleteLater()


def test_inventory_item_type_hints_word_wrap(db_session):
    dlg = ProductEditor()
    try:
        hints = [
            dlg.weighted_hint,
            dlg.service_hint,
            dlg.price_change_hint,
            dlg.age_restricted_hint,
        ]
        for hint in hints:
            assert hint.wordWrap()
            assert hint.sizePolicy().horizontalPolicy() == QSizePolicy.Policy.Expanding
            assert hint.sizePolicy().verticalPolicy() == QSizePolicy.Policy.Minimum
    finally:
        dlg.deleteLater()


def test_qss_has_inventory_scroll_rules():
    from pathlib import Path

    style_dir = Path(__file__).parent.parent.parent / "cbpos" / "ui" / "styles"
    dark_qss = (style_dir / "dark.qss").read_text()
    light_qss = (style_dir / "light.qss").read_text()
    assert "QScrollArea#InventoryScrollArea" in dark_qss
    assert "QWidget#InventoryScrollInner" in dark_qss
    assert "QScrollArea#InventoryScrollArea" in light_qss
    assert "QWidget#InventoryScrollInner" in light_qss
