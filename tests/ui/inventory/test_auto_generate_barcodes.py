"""#641: Settings -> System -> "Auto-Generate Barcodes" ("Auto-generate
barcodes for new products without one") was saved but never read -- the
Product Editor always refused a blank barcode. With the setting on, a new
product saved without a barcode gets a unique in-store EAN-13; off, a
barcode is still required.
"""

from decimal import Decimal

import pytest
from PyQt6.QtWidgets import QMessageBox

from cbpos.core.models import Product
from cbpos.core.services.config_service import ConfigService
from cbpos.core.services.inventory_service import InventoryService
from cbpos.core.services.scale_service import ScaleService
from cbpos.ui.dialogs.product_editor import ProductEditor

pytestmark = pytest.mark.usefixtures("qapp")


@pytest.fixture
def setting(monkeypatch):
    def _set(value: bool):
        real_get = ConfigService.get
        monkeypatch.setattr(
            ConfigService,
            "get",
            staticmethod(lambda key: value if key == "auto_generate_barcodes" else real_get(key)),
        )

    return _set


def _new(name: str) -> dict:
    return {"barcode": "", "name_en": name, "price": Decimal("50"), "cost": Decimal("0")}


class TestServiceGeneratesBarcode:
    def test_blank_barcode_gets_a_valid_in_store_ean13(self, db_session, setting):
        setting(True)

        product = InventoryService().create_product(_new("AutoBarcode One"))

        assert len(product.barcode) == 13
        assert product.barcode.isdigit()
        assert product.barcode.startswith("2")  # GS1 in-store range, never a real maker's code
        assert ScaleService._validate_ean13_checksum(product.barcode)

    def test_two_new_products_get_different_barcodes(self, db_session, setting):
        setting(True)
        service = InventoryService()

        first = service.create_product(_new("AutoBarcode A"))
        second = service.create_product(_new("AutoBarcode B"))

        assert first.barcode != second.barcode

    def test_a_typed_barcode_is_kept(self, db_session, setting):
        setting(True)

        product = InventoryService().create_product({**_new("AutoBarcode Typed"), "barcode": "TYPED-641"})

        assert product.barcode == "TYPED-641"


class TestEditorAllowsBlankBarcode:
    def test_on_saves_a_new_product_with_no_barcode_typed(self, db_session, setting, monkeypatch):
        setting(True)
        monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: pytest.fail("blocked by a warning"))
        dialog = ProductEditor()
        dialog.name_en_input.setText("AutoBarcode From Editor")
        dialog.price_input.setText("75")

        dialog.save_product()

        saved = db_session.query(Product).filter_by(name_en="AutoBarcode From Editor").one()
        assert len(saved.barcode) == 13

    def test_off_still_requires_a_barcode(self, db_session, setting, monkeypatch):
        setting(False)
        warned = []
        monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: warned.append(a[2]))
        dialog = ProductEditor()
        dialog.name_en_input.setText("AutoBarcode Off")
        dialog.price_input.setText("75")

        dialog.save_product()

        assert warned
        assert db_session.query(Product).filter_by(name_en="AutoBarcode Off").first() is None
