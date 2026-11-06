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

    def test_age_restricted_checkbox_defaults_to_unchecked(self, db_session):
        dialog = ProductEditor()
        assert dialog.age_restricted_check.isChecked() is False

    def test_age_restricted_round_trips_through_load_and_save(self, db_session):
        product = Product(
            barcode="PE-TEST-4",
            name_en="Alcohol Product",
            price=Decimal("500.00"),
            cost=Decimal("300.00"),
            is_age_restricted=True,
        )
        db_session.add(product)
        db_session.flush()

        dialog = ProductEditor(product=product)
        assert dialog.age_restricted_check.isChecked() is True

        dialog.age_restricted_check.setChecked(False)
        dialog.save_product()

        db_session.expire_all()
        saved = db_session.query(Product).filter_by(barcode="PE-TEST-4").one()
        assert saved.is_age_restricted is False

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


class TestProductEditorIssue862UI:
    def test_issue_862_editor_shows_read_only_stock_and_cost_for_existing_product(self, db_session):
        product = Product(
            barcode="PE-ISSUE-862",
            name_en="Read Only Fields Product",
            price=Decimal("150.00"),
            cost=Decimal("90.00"),
            stock_qty=Decimal("25.000"),
        )
        db_session.add(product)
        db_session.flush()

        dialog = ProductEditor(product=product)

        assert dialog.cost_input.isReadOnly() is True
        assert dialog.stock_input.isReadOnly() is True
        assert hasattr(dialog, "btn_set_cost")
        assert hasattr(dialog, "btn_adjust_stock")
        assert dialog.stock_input.text() == "25.000"
        assert dialog.cost_input.text() == "90.00"

    def test_issue_862_stale_product_save_shows_warning(self, db_session, monkeypatch):
        product = Product(
            barcode="PE-ISSUE-862-STALE",
            name_en="Concurrent Product",
            price=Decimal("200.00"),
            cost=Decimal("100.00"),
            stock_qty=Decimal("10.000"),
        )
        db_session.add(product)
        db_session.commit()

        dialog = ProductEditor(product=product)

        # Advance version in DB to make the dialog's snapshot stale
        with dialog.inventory_service.db.get_session() as s2:
            p2 = s2.get(Product, product.id)
            p2.price = Decimal("250.00")
            s2.commit()

        warnings = []
        monkeypatch.setattr("cbpos.ui.dialogs.product_editor.QMessageBox.warning", lambda *args: warnings.append(args))
        accepted = []
        monkeypatch.setattr(dialog, "accept", lambda: accepted.append(True))

        dialog.name_en_input.setText("Updated Concurrently")
        dialog.save_product()

        assert len(warnings) == 1
        assert len(accepted) == 0
