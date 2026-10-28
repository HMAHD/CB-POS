"""Tests for issue #700: extract inline QDialog classes from view modules into dialogs package."""

import pytest

import cbpos.core.models  # noqa: F401 - registers all ORM tables with Base.metadata

pytestmark = pytest.mark.usefixtures("qapp", "db_session")


def test_import_from_dialogs_package():
    from cbpos.ui.dialogs.grn_detail_dialog import GRNDetailDialog
    from cbpos.ui.dialogs.payment_method_dialog import PaymentMethodDialog
    from cbpos.ui.dialogs.price_list_dialog import PriceListDialog
    from cbpos.ui.dialogs.promotion_dialog import PromotionDialog
    from cbpos.ui.dialogs.stock_count_report_dialog import StockCountReportDialog
    from cbpos.ui.dialogs.supplier_dialog import SupplierDialog
    from cbpos.ui.dialogs.user_dialog import UserDialog

    assert callable(GRNDetailDialog)
    assert callable(SupplierDialog)
    assert callable(StockCountReportDialog)
    assert callable(PriceListDialog)
    assert callable(PaymentMethodDialog)
    assert callable(PromotionDialog)
    assert callable(UserDialog)


def test_backward_compatible_imports_from_views():
    from cbpos.ui.views.payment_methods_view import PaymentMethodDialog
    from cbpos.ui.views.pricelist_view import PriceListDialog
    from cbpos.ui.views.promotion_view import PromotionDialog
    from cbpos.ui.views.purchase_view import GRNDetailDialog, SupplierDialog
    from cbpos.ui.views.stock_take_view import StockCountReportDialog
    from cbpos.ui.views.user_view import UserDialog

    assert callable(GRNDetailDialog)
    assert callable(SupplierDialog)
    assert callable(StockCountReportDialog)
    assert callable(PriceListDialog)
    assert callable(PaymentMethodDialog)
    assert callable(PromotionDialog)
    assert callable(UserDialog)


def test_instantiate_extracted_dialogs(qapp, db_session):
    from cbpos.ui.dialogs.grn_detail_dialog import GRNDetailDialog
    from cbpos.ui.dialogs.payment_method_dialog import PaymentMethodDialog
    from cbpos.ui.dialogs.price_list_dialog import PriceListDialog
    from cbpos.ui.dialogs.promotion_dialog import PromotionDialog
    from cbpos.ui.dialogs.stock_count_report_dialog import StockCountReportDialog
    from cbpos.ui.dialogs.supplier_dialog import SupplierDialog
    from cbpos.ui.dialogs.user_dialog import UserDialog

    # Test instantiation of standalone dialogs
    dlg_supplier = SupplierDialog()
    assert dlg_supplier.windowTitle() != ""
    assert dlg_supplier.objectName() == "SupplierDialog"
    dlg_supplier.close()

    dlg_grn = GRNDetailDialog(purchase_id=999999)  # Non-existent purchase displays not found message
    assert dlg_grn.windowTitle() != ""
    dlg_grn.close()

    dlg_stock = StockCountReportDialog(stock_count_id=999999)  # Non-existent count
    assert dlg_stock.windowTitle() != ""
    dlg_stock.close()

    dlg_price = PriceListDialog()
    assert dlg_price.windowTitle() != ""
    dlg_price.close()

    dlg_pm = PaymentMethodDialog()
    assert dlg_pm.objectName() == "PaymentMethodDialog"
    dlg_pm.close()

    dlg_promo = PromotionDialog()
    assert dlg_promo.windowTitle() != ""
    dlg_promo.close()

    dlg_user = UserDialog()
    assert dlg_user.windowTitle() != ""
    dlg_user.close()
