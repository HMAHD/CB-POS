"""
#627 (UI-056): TransactionService.void_sale() takes a reason, but the
Document Browser's Void button called it with two arguments, so every void
died with a TypeError shown as "Void failed". The button now asks for a
VoidReason (plus optional note) and passes it through; the
require_void_reason setting decides whether a reason is mandatory.
"""

from datetime import datetime
from decimal import Decimal

import pytest
from PyQt6.QtWidgets import QDialog

from cbpos.core.models import AuditLog, Product, Role, Sale, SaleItem, StockMovement, User, VoidReason
from cbpos.core.services.transaction_service import TransactionService
from cbpos.ui.dialogs.void_reason_dialog import VoidReasonDialog
from cbpos.ui.views.document_view import DocumentBrowserView

pytestmark = pytest.mark.usefixtures("qapp")

_counter = 0


def _next() -> str:
    global _counter
    _counter += 1
    return str(_counter)


@pytest.fixture
def user(db_session):
    suffix = _next()
    role = Role(name=f"VoidRole_{suffix}")
    user = User(username=f"void_user_{suffix}", pin_hash="hash", role=role, is_active=True)
    db_session.add_all([role, user])
    db_session.flush()
    return user


@pytest.fixture
def reason(db_session):
    reason = VoidReason(code=f"VMISTAKE{_next()}", description="Cashier Mistake")
    db_session.add(reason)
    db_session.flush()
    return reason


@pytest.fixture
def sale(db_session, user):
    suffix = _next()
    product = Product(name_en=f"Void Product {suffix}", barcode=f"VOID-{suffix}", price=Decimal("50"), stock_qty=10)
    db_session.add(product)
    db_session.flush()
    sale = Sale(
        document_number=f"REC-VOID-{suffix}",
        date=datetime.now(),
        total_amount=Decimal("100.00"),
        user_id=user.id,
        tax_vat=0,
        tax_sscl=0,
        net_revenue=100,
        payment_method="CASH",
        status="COMPLETED",
    )
    sale.items.append(
        SaleItem(
            product_id=product.id,
            qty=Decimal("2"),
            unit_price=Decimal("50"),
            original_price=Decimal("50"),
            subtotal=Decimal("100"),
        )
    )
    db_session.add(sale)
    db_session.commit()
    return sale


class _FakeVoidDialog:
    """Stands in for VoidReasonDialog: records how it was built, returns a fixed choice."""

    built_with: dict = {}
    result = QDialog.DialogCode.Accepted
    reason_id = None
    reason_text = ""

    def __init__(self, reasons, require_reason, doc_number, parent=None):
        type(self).built_with = {"reasons": reasons, "require_reason": require_reason, "doc_number": doc_number}

    def exec(self):
        return self.result


@pytest.fixture
def view(qapp, db_session, user, monkeypatch):
    import cbpos.core.utils.permission_helper as permission_helper

    monkeypatch.setattr(permission_helper, "check_permission_with_override", lambda perm, parent: user)
    monkeypatch.setattr("cbpos.ui.views.document_view.AuthService.get_current_user", lambda: user)
    monkeypatch.setattr("cbpos.ui.views.document_view.QMessageBox.question", lambda *a, **k: None)
    monkeypatch.setattr("cbpos.ui.views.document_view.QMessageBox.information", lambda *a, **k: None)
    v = DocumentBrowserView()
    monkeypatch.setattr(v, "load_documents", lambda: None)
    yield v
    v.deleteLater()


def _doc(sale):
    return {"id": sale.id, "type": "sale", "status": "COMPLETED", "document_number": sale.document_number}


class TestVoidButtonHandler:
    def test_void_succeeds_records_reason_and_reverses_stock(self, view, db_session, sale, user, reason, monkeypatch):
        errors = []
        monkeypatch.setattr("cbpos.ui.views.document_view.QMessageBox.critical", lambda *a, **k: errors.append(a))
        monkeypatch.setattr("cbpos.ui.views.document_view.VoidReasonDialog", _FakeVoidDialog, raising=False)
        _FakeVoidDialog.result = QDialog.DialogCode.Accepted
        _FakeVoidDialog.reason_id = reason.id
        _FakeVoidDialog.reason_text = "Cashier Mistake - scanned twice"

        view.current_doc = _doc(sale)
        view.void_document()

        assert errors == []
        db_session.expire_all()
        voided = db_session.get(Sale, sale.id)
        assert voided.status == "VOID"
        assert voided.void_reason_id == reason.id
        log = db_session.query(AuditLog).filter_by(action="VOID_SALE").order_by(AuditLog.id.desc()).first()
        assert sale.document_number in log.details
        assert "Cashier Mistake - scanned twice" in log.details
        movements = db_session.query(StockMovement).filter_by(document_id=sale.id, type="VOID").all()
        assert [m.qty_change for m in movements] == [Decimal("2")]
        assert any(r["id"] == reason.id for r in _FakeVoidDialog.built_with["reasons"])

    def test_setting_is_passed_to_the_dialog(self, view, sale, reason, monkeypatch):
        from cbpos.core.services.config_service import ConfigService

        monkeypatch.setattr("cbpos.ui.views.document_view.VoidReasonDialog", _FakeVoidDialog, raising=False)
        _FakeVoidDialog.result = QDialog.DialogCode.Rejected
        monkeypatch.setattr(ConfigService, "get", classmethod(lambda cls, key: key != "require_void_reason"))

        view.current_doc = _doc(sale)
        view.void_document()

        assert _FakeVoidDialog.built_with["require_reason"] is False

    def test_cancelling_the_dialog_does_not_void(self, view, db_session, sale, monkeypatch):
        monkeypatch.setattr("cbpos.ui.views.document_view.VoidReasonDialog", _FakeVoidDialog, raising=False)
        _FakeVoidDialog.result = QDialog.DialogCode.Rejected

        view.current_doc = _doc(sale)
        view.void_document()

        db_session.expire_all()
        assert db_session.get(Sale, sale.id).status == "COMPLETED"

    def test_issue_848_document_browser_disables_void_for_refund_document(self, view):
        """Document browser disables Void button for refund/credit note documents."""
        refund_doc = {
            "type": "sale",
            "status": "COMPLETED",
            "doc_number": "CN-2026-0001",
            "payment_method": "REFUND",
            "refund_of_sale_id": 42,
        }
        view.update_action_buttons(refund_doc)
        assert view.void_btn.isEnabled() is False


class TestVoidReasonDialog:
    REASONS = [{"id": 1, "code": "MISTAKE", "description": "Cashier Mistake"}]

    def test_required_reason_blocks_accept_until_chosen(self):
        dlg = VoidReasonDialog(self.REASONS, True, "REC-1")
        assert dlg.objectName() == "VoidReasonDialog"
        assert dlg.btn_void.isEnabled() is False
        dlg.cmb_reason.setCurrentIndex(1)
        assert dlg.btn_void.isEnabled() is True
        dlg.txt_note.setText("scanned twice")
        dlg._accept()
        assert dlg.result() == QDialog.DialogCode.Accepted
        assert dlg.reason_id == 1
        assert dlg.reason_text == "Cashier Mistake - scanned twice"

    def test_optional_reason_allows_void_without_one(self):
        dlg = VoidReasonDialog(self.REASONS, False, "REC-1")
        assert dlg.btn_void.isEnabled() is True
        dlg._accept()
        assert dlg.reason_id is None
        assert dlg.reason_text == ""


class TestVoidSaleService:
    def test_void_sale_stores_reason_id(self, db_session, sale, user, reason):
        assert TransactionService.void_sale(sale.id, user.id, "Cashier Mistake", reason_id=reason.id)
        db_session.expire_all()
        assert db_session.get(Sale, sale.id).void_reason_id == reason.id

    def test_get_void_reasons_lists_rows(self, db_session, reason):
        reasons = TransactionService.get_void_reasons()
        assert {"id": reason.id, "code": reason.code, "description": "Cashier Mistake"} in reasons
