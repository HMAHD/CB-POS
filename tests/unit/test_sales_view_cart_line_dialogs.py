"""
"Change Quantity" (F4) and "Change Price" (Manager-only) on an existing
cart line used QInputDialog.getDouble() -- a stock Qt dialog whose
embedded spin box and OK/Cancel buttons are native widgets with no
objectName, so none of this app's QSS can reach them. Meanwhile adding a
*new* product to the cart already uses the fully-styled QuantityDialog.
This replaces change_line_quantity() with QuantityDialog (pre-filled with
the line's current qty) and change_line_price() with SetItemPriceDialog
(already built for #369's price-list editor), so both actions match the
rest of the cart workflow.
"""

from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from cbpos.infrastructure.hardware.escpos_driver import PrintWorker
from cbpos.ui.views import sales_view as sales_view_module
from cbpos.ui.views.sales_view import SalesView

pytestmark = pytest.mark.usefixtures("qapp")


@pytest.fixture(autouse=True)
def _shutdown_print_worker():
    yield
    PrintWorker.shutdown()


@pytest.fixture
def view(qapp, db_session):
    v = SalesView()
    yield v
    v.deleteLater()


def _make_product(price="200.00"):
    product = MagicMock()
    product.id = 1
    product.name_en = "Test Product"
    product.barcode = "TEST001"
    product.price = Decimal(price)
    product.stock_qty = Decimal("10")
    product.unit = None
    return product


class TestChangeLineQuantityUsesStyledDialog:
    def test_confirming_the_dialog_updates_qty_and_total(self, view):
        view.cart_service.add_item(_make_product(), qty=Decimal("2"))
        view.update_cart_display()
        view.cart_table.setCurrentCell(0, 0)

        fake_dialog = MagicMock()
        fake_dialog.exec.return_value = 1
        fake_dialog.get_quantity.return_value = Decimal("5")
        fake_dialog_cls = MagicMock(return_value=fake_dialog)

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(sales_view_module, "QuantityDialog", fake_dialog_cls)
            view.change_line_quantity()

        args, kwargs = fake_dialog_cls.call_args
        assert kwargs["initial_qty"] == Decimal("2")

        assert view.cart_service.items[0]["qty"] == Decimal("5")
        assert view.cart_service.items[0]["total"] == Decimal("5") * view.cart_service.items[0]["unit_price"]

    def test_cancelling_the_dialog_leaves_qty_unchanged(self, view):
        view.cart_service.add_item(_make_product(), qty=Decimal("2"))
        view.update_cart_display()
        view.cart_table.setCurrentCell(0, 0)

        fake_dialog = MagicMock()
        fake_dialog.exec.return_value = 0
        fake_dialog_cls = MagicMock(return_value=fake_dialog)

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(sales_view_module, "QuantityDialog", fake_dialog_cls)
            view.change_line_quantity()

        assert view.cart_service.items[0]["qty"] == Decimal("2")


class TestChangeLinePriceUsesStyledDialog:
    def test_confirming_the_dialog_overrides_the_price(self, view, monkeypatch):
        from cbpos.core.models import User

        manager = User(username="mgr", pin_hash="x", role_id=None, is_active=True)
        import cbpos.core.utils.permission_helper as permission_helper

        monkeypatch.setattr(permission_helper, "check_permission_with_override", lambda perm, parent: manager)

        view.cart_service.add_item(_make_product(price="200.00"))
        view.update_cart_display()
        view.cart_table.setCurrentCell(0, 0)

        fake_dialog = MagicMock()
        fake_dialog.exec.return_value = 1
        fake_dialog.get_price.return_value = Decimal("175.00")
        fake_dialog_cls = MagicMock(return_value=fake_dialog)

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(sales_view_module, "SetItemPriceDialog", fake_dialog_cls)
            view.change_line_price()

        args, _ = fake_dialog_cls.call_args
        assert args[0] == "Test Product"
        assert view.cart_service.items[0]["unit_price"] == Decimal("175.00")
