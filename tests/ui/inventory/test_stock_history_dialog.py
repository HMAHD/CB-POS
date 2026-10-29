"""Stock History dialog opens for a product with movements (#631, UI-059).

The dialog used to read ``StockMovement.reference`` (no such attribute) and
lazy-loaded ``move.user`` off an expunged row, so it crashed on every open.
"""

from decimal import Decimal

from cbpos.core.models import Permission, Product, Role, Sale, User
from cbpos.core.services.stock_service import StockService
from cbpos.i18n import _t
from cbpos.ui.dialogs.stock_history_dialog import StockHistoryDialog


def test_stock_history_dialog_shows_document_number_or_type(qapp, db_session):
    permission = Permission(code="stock_hist_test")
    role = Role(name="StockHistRole", permissions=[permission])
    user = User(username="stock_hist_user", pin_hash="hash", role=role)
    product = Product(name_en="StockHistProduct", price=Decimal("100"), stock_qty=Decimal("10"), barcode="SH0001")
    db_session.add_all([permission, role, user, product])
    db_session.flush()
    sale = Sale(document_number="REC-SH-0001", user_id=user.id, total_amount=Decimal("100"), payment_method="Cash")
    db_session.add(sale)
    db_session.flush()

    StockService.record_movement(product.id, Decimal("-1"), "SALE", user.id, document_id=sale.id, session=db_session)
    StockService.record_movement(product.id, Decimal("5"), "ADJUSTMENT", user.id, session=db_session)
    db_session.commit()

    dialog = StockHistoryDialog(product)
    try:
        rows = {
            dialog.table.item(r, 1).text(): (dialog.table.item(r, 2).text(), dialog.table.item(r, 3).text())
            for r in range(dialog.table.rowCount())
        }
        assert rows[_t("stock_history.type_sale")] == ("REC-SH-0001", "stock_hist_user")
        assert rows[_t("stock_history.type_adjustment")] == ("", "stock_hist_user")
    finally:
        dialog.deleteLater()
