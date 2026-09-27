"""
Product Editor's Selling Price and Cost Price fields used a plain
QDoubleSpinBox even though this same file already flagged that exact
widget as broken under this app's QSS ("Stock group -- QLineEdit instead
of QDoubleSpinBox for clean rendering (QDoubleSpinBox +/- buttons break
under QSS)") and migrated Stock/Reorder Point/Preferred Qty away from it.
Selling Price, Cost Price, and the Composition tab's quantity field were
never migrated.
"""

from decimal import Decimal

import pytest
from PyQt6.QtWidgets import QLineEdit

from cbpos.core.models import Product
from cbpos.ui.dialogs.product_editor import ProductEditor

pytestmark = pytest.mark.usefixtures("qapp")


class TestPriceFieldWidgets:
    def test_price_cost_and_component_qty_use_line_edit_not_spinbox(self, db_session):
        dialog = ProductEditor()

        assert isinstance(dialog.price_input, QLineEdit)
        assert isinstance(dialog.cost_input, QLineEdit)
        assert isinstance(dialog.comp_qty_input, QLineEdit)


class TestPriceFieldDataRoundTrip:
    def test_load_data_populates_price_and_cost_text(self, db_session):
        product = Product(
            barcode="PE-TEST-1", name_en="Existing Product", price=Decimal("299.50"), cost=Decimal("150.25")
        )
        db_session.add(product)
        db_session.flush()

        dialog = ProductEditor(product=product)

        assert dialog.price_input.text() == "299.50"
        assert dialog.cost_input.text() == "150.25"

    def test_save_parses_price_and_cost_from_text_fields(self, db_session):
        dialog = ProductEditor()
        dialog.name_en_input.setText("New Priced Product")
        dialog.barcode_input.setText("PE-TEST-2")
        dialog.price_input.setText("499.99")
        dialog.cost_input.setText("250.00")

        dialog.save_product()

        saved = db_session.query(Product).filter_by(barcode="PE-TEST-2").one()
        assert saved.price == Decimal("499.99")
        assert saved.cost == Decimal("250.00")

    def test_price_change_allowed_checkbox_defaults_to_checked(self, db_session):
        dialog = ProductEditor()
        assert dialog.price_change_allowed_check.isChecked() is True

    def test_price_change_allowed_round_trips_through_load_and_save(self, db_session):
        product = Product(
            barcode="PE-TEST-3",
            name_en="Regulated Product",
            price=Decimal("100.00"),
            cost=Decimal("50.00"),
            price_change_allowed=False,
        )
        db_session.add(product)
        db_session.flush()

        dialog = ProductEditor(product=product)
        assert dialog.price_change_allowed_check.isChecked() is False

        dialog.price_change_allowed_check.setChecked(True)
        dialog.save_product()

        db_session.expire_all()
        saved = db_session.query(Product).filter_by(barcode="PE-TEST-3").one()
        assert saved.price_change_allowed is True

    def test_add_component_parses_quantity_from_text_field(self, db_session):
        child = Product(barcode="PE-CHILD-1", name_en="Component Product", price=Decimal("10.00"), cost=Decimal("5.00"))
        db_session.add(child)
        db_session.flush()

        dialog = ProductEditor()
        dialog.comp_qty_input.setText("2.50")
        dialog.comp_barcode_input.setText("PE-CHILD-1")

        dialog.add_component()

        assert dialog.comp_table.rowCount() == 1
        assert dialog.comp_table.item(0, 2).text() == "2.50"
