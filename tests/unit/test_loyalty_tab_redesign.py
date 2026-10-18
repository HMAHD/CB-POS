import pytest

from cbpos.core.models import Customer
from cbpos.ui.dialogs.customer_editor import CustomerEditor

pytestmark = pytest.mark.usefixtures("qapp")


def test_new_customer_loyalty_tab_disables_adjust_points(db_session):
    # Customer without ID (new customer)
    editor = CustomerEditor(None)
    try:
        assert not editor.btn_adjust_points.isEnabled()
        assert "Save the customer first" in editor.btn_adjust_points.toolTip()
    finally:
        editor.deleteLater()


def test_existing_customer_loyalty_tab_enables_adjust_points(db_session):
    cust = Customer(
        name="Existing Loyalty Cust",
        phone="0771239999",
        loyalty_points=250,
    )
    db_session.add(cust)
    db_session.flush()

    editor = CustomerEditor(cust)
    try:
        assert editor.btn_adjust_points.isEnabled()
    finally:
        editor.deleteLater()
