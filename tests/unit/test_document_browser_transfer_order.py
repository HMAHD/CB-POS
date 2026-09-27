"""
#479: TransactionService.transfer_order() existed but was called from
nowhere in the UI -- dead code. Wires it into the Document Browser's action
row as a "Transfer" button (Lock Order was explicitly not built -- flagged
as unneeded by product decision, roadmap corrected instead).
"""

from datetime import datetime
from decimal import Decimal

import pytest

from cbpos.core.models import Role, Sale, User
from cbpos.ui.views.document_view import DocumentBrowserView

pytestmark = pytest.mark.usefixtures("qapp")

_counter = 0


@pytest.fixture
def owner_user(db_session):
    global _counter
    _counter += 1
    suffix = str(_counter)
    role = Role(name=f"TransferOwnerRole_{suffix}")
    user = User(username=f"transfer_owner_{suffix}", pin_hash="hash", role=role, is_active=True)
    db_session.add_all([role, user])
    db_session.flush()
    return user


@pytest.fixture
def target_user(db_session):
    global _counter
    _counter += 1
    suffix = str(_counter)
    role = Role(name=f"TransferTargetRole_{suffix}")
    user = User(username=f"transfer_target_{suffix}", pin_hash="hash", role=role, is_active=True)
    db_session.add_all([role, user])
    db_session.flush()
    return user


@pytest.fixture
def sale(db_session, owner_user):
    global _counter
    _counter += 1
    sale = Sale(
        document_number=f"REC-XFER-{_counter}",
        date=datetime.now(),
        total_amount=Decimal("100.00"),
        user_id=owner_user.id,
        tax_vat=0,
        tax_sscl=0,
        net_revenue=100,
        payment_method="CASH",
        status="COMPLETED",
    )
    db_session.add(sale)
    db_session.commit()
    return sale


@pytest.fixture
def view(qapp, db_session):
    v = DocumentBrowserView()
    yield v
    v.deleteLater()


def _current_doc(sale, owner_user):
    return {
        "id": sale.id,
        "type": "sale",
        "status": "COMPLETED",
        "document_number": sale.document_number,
        "username": owner_user.username,
    }


class TestTransferButtonEnablement:
    def test_enabled_for_a_completed_sale(self, view, sale, owner_user):
        view.update_action_buttons(_current_doc(sale, owner_user))
        assert view.transfer_btn.isEnabled() is True

    def test_disabled_for_a_voided_sale(self, view, sale, owner_user):
        doc = _current_doc(sale, owner_user)
        doc["status"] = "VOID"
        view.update_action_buttons(doc)
        assert view.transfer_btn.isEnabled() is False

    def test_disabled_for_a_purchase_document(self, view, sale, owner_user):
        doc = _current_doc(sale, owner_user)
        doc["type"] = "purchase"
        view.update_action_buttons(doc)
        assert view.transfer_btn.isEnabled() is False


class TestTransferOrderRequiresPermission:
    def test_denied_permission_never_prompts_for_a_target_user(self, view, db_session, sale, owner_user, monkeypatch):
        import cbpos.core.utils.permission_helper as permission_helper

        monkeypatch.setattr(permission_helper, "check_permission_with_override", lambda perm, parent: None)

        prompted = []
        monkeypatch.setattr(
            "cbpos.ui.views.document_view.QInputDialog.getItem",
            lambda *a, **k: prompted.append(True) or ("", False),
        )

        view.current_doc = _current_doc(sale, owner_user)
        view.transfer_order()

        assert prompted == []
        db_session.expire_all()
        assert db_session.get(Sale, sale.id).user_id == owner_user.id


class TestTransferOrderReassignsTheSale:
    def test_selecting_a_target_user_reassigns_the_sale(
        self, view, db_session, sale, owner_user, target_user, monkeypatch
    ):
        import cbpos.core.utils.permission_helper as permission_helper

        monkeypatch.setattr(permission_helper, "check_permission_with_override", lambda perm, parent: owner_user)
        monkeypatch.setattr(
            "cbpos.ui.views.document_view.QInputDialog.getItem",
            lambda *a, **k: (target_user.username, True),
        )
        monkeypatch.setattr("cbpos.ui.views.document_view.QMessageBox.information", lambda *a, **k: None)
        monkeypatch.setattr(view, "load_documents", lambda: None)

        view.current_doc = _current_doc(sale, owner_user)
        view.transfer_order()

        db_session.expire_all()
        assert db_session.get(Sale, sale.id).user_id == target_user.id

    def test_the_current_owner_is_not_offered_as_a_transfer_target(
        self, view, db_session, sale, owner_user, target_user, monkeypatch
    ):
        import cbpos.core.utils.permission_helper as permission_helper

        monkeypatch.setattr(permission_helper, "check_permission_with_override", lambda perm, parent: owner_user)

        seen_usernames = []

        def fake_get_item(parent, title, label, items, current, editable):
            seen_usernames.extend(items)
            return ("", False)

        monkeypatch.setattr("cbpos.ui.views.document_view.QInputDialog.getItem", fake_get_item)

        view.current_doc = _current_doc(sale, owner_user)
        view.transfer_order()

        assert owner_user.username not in seen_usernames
        assert target_user.username in seen_usernames

    def test_declining_the_picker_does_not_reassign(self, view, db_session, sale, owner_user, target_user, monkeypatch):
        import cbpos.core.utils.permission_helper as permission_helper

        monkeypatch.setattr(permission_helper, "check_permission_with_override", lambda perm, parent: owner_user)
        monkeypatch.setattr(
            "cbpos.ui.views.document_view.QInputDialog.getItem",
            lambda *a, **k: ("", False),
        )

        view.current_doc = _current_doc(sale, owner_user)
        view.transfer_order()

        db_session.expire_all()
        assert db_session.get(Sale, sale.id).user_id == owner_user.id
