"""
#639: renaming a payment method that is already used bypassed delete protection.

Sale payments store the method *name* as text, and ``delete_method`` decided
"used" by that name. Renaming a used method, then deleting it, hard-deleted
it -- and the rename alone split report history (old sales kept the old name).
A used method's name is now locked, and the UI never offers Delete for it.
"""

from datetime import datetime
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from PyQt6.QtWidgets import QMessageBox

from cbpos.core.models import CustomerPayment, PaymentMethod, Permission, Role, Sale, SalePayment, User
from cbpos.core.services.payment_service import PaymentMethodInUseError, PaymentService
from cbpos.ui.views.payment_methods_view import PaymentMethodDialog, PaymentMethodsView, _MethodCard

_counter = 0


def _new_method(db_session, name: str) -> PaymentMethod:
    m = PaymentMethod(name=name, is_cash=False, is_active=True)
    db_session.add(m)
    db_session.commit()
    return m


@pytest.fixture
def user(db_session):
    global _counter
    _counter += 1
    permission = Permission(code=f"pm639_{_counter}")
    role = Role(name=f"PM639Role_{_counter}", permissions=[permission])
    u = User(username=f"pm639_{_counter}", pin_hash="hash", role=role)
    db_session.add_all([permission, role, u])
    db_session.flush()
    return u


@pytest.fixture
def used_method(db_session, user):
    """A method with one sale paid by it (stored by name, as checkout does)."""
    global _counter
    _counter += 1
    method = _new_method(db_session, f"Wallet639_{_counter}")
    sale = Sale(
        document_number=f"REC-639-{_counter}",
        date=datetime.now(),
        total_amount=Decimal("100.00"),
        user_id=user.id,
        payment_method=method.name,
        status="COMPLETED",
    )
    db_session.add(sale)
    db_session.flush()
    db_session.add(SalePayment(sale_id=sale.id, payment_method=method.name, amount=Decimal("100.00")))
    db_session.commit()
    return method


@pytest.fixture
def unused_method(db_session):
    global _counter
    _counter += 1
    return _new_method(db_session, f"Fresh639_{_counter}")


class TestRenameRule:
    def test_used_method_cannot_be_renamed(self, db_session, used_method):
        with pytest.raises(PaymentMethodInUseError):
            PaymentService.update_method(used_method.id, name="Renamed639")

        db_session.expire_all()
        assert db_session.get(PaymentMethod, used_method.id).name == used_method.name

    def test_rename_then_delete_of_used_method_only_deactivates(self, db_session, used_method):
        with pytest.raises(PaymentMethodInUseError):
            PaymentService.update_method(used_method.id, name="Renamed639")

        assert PaymentService.delete_method(used_method.id) is True

        db_session.expire_all()
        method = db_session.get(PaymentMethod, used_method.id)
        assert method is not None
        assert method.is_active is False

    def test_used_method_can_still_be_edited_without_renaming(self, used_method):
        updated = PaymentService.update_method(used_method.id, name=used_method.name, open_drawer=True, shortcut="F7")
        assert updated.open_drawer is True
        assert updated.shortcut == "F7"

    def test_unused_method_can_be_renamed_and_deleted(self, db_session, unused_method):
        PaymentService.update_method(unused_method.id, name=unused_method.name + "_x")
        assert PaymentService.delete_method(unused_method.id) is True

        db_session.expire_all()
        assert db_session.get(PaymentMethod, unused_method.id) is None

    def test_name_match_is_case_insensitive(self, db_session, user):
        method = _new_method(db_session, "Mixed639")
        sale = Sale(
            document_number="REC-639-CASE",
            date=datetime.now(),
            total_amount=Decimal("1"),
            user_id=user.id,
            payment_method="SPLIT",
        )
        db_session.add(sale)
        db_session.flush()
        db_session.add(SalePayment(sale_id=sale.id, payment_method="MIXED639", amount=Decimal("1")))
        db_session.commit()

        assert PaymentService.is_method_used(method.id) is True

    def test_credit_book_payment_counts_as_use(self, db_session, user):
        from cbpos.core.models import Customer

        method = _new_method(db_session, "Book639")
        customer = Customer(name="PM639 customer")
        db_session.add(customer)
        db_session.flush()
        db_session.add(
            CustomerPayment(customer_id=customer.id, amount=Decimal("5"), payment_method="Book639", user_id=user.id)
        )
        db_session.commit()

        assert PaymentService.is_method_used(method.id) is True

    def test_used_method_ids(self, used_method, unused_method):
        used = PaymentService.get_used_method_ids()
        assert used_method.id in used
        assert unused_method.id not in used


def _card_method(name="Card639", is_cash=False):
    method = MagicMock(spec=PaymentMethod)
    method.id = 1
    method.name = name
    method.is_cash = is_cash
    method.is_active = True
    method.open_drawer = False
    method.shortcut = None
    return method


@pytest.mark.usefixtures("qapp")
class TestUi:
    def test_card_never_offers_delete_for_a_used_method(self):
        card = _MethodCard(_card_method(), MagicMock(), has_history=True)
        assert card.btn_delete.isVisibleTo(card) is False
        assert card.btn_delete.sizePolicy().retainSizeWhenHidden() is True

    def test_card_offers_delete_for_an_unused_method(self):
        card = _MethodCard(_card_method(), MagicMock(), has_history=False)
        assert card.btn_delete.isVisibleTo(card) is True

    def test_edit_dialog_locks_the_name_of_a_used_method(self):
        dialog = PaymentMethodDialog(method=_card_method(), name_locked=True)
        assert dialog.txt_name.isReadOnly() is True
        assert dialog.lbl_name_locked.isVisibleTo(dialog) is True

    def test_edit_dialog_leaves_an_unused_name_editable(self):
        dialog = PaymentMethodDialog(method=_card_method())
        assert dialog.txt_name.isReadOnly() is False
        assert dialog.lbl_name_locked.isVisibleTo(dialog) is False

    def test_delete_that_became_a_deactivate_tells_the_user(self, used_method):
        view = PaymentMethodsView()
        with (
            patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes),
            patch.object(QMessageBox, "information") as info,
        ):
            view._delete_method(used_method)
        info.assert_called_once()
        view.deleteLater()
