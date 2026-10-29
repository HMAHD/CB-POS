"""
#403: the customer_statement.opening/sales/payments/closing templates
had no {value} placeholder at all, so _t(key, value=...) always
rendered as just "Opening Balance:" etc -- str.format() silently
ignores extra kwargs that don't match a placeholder, with no error --
meaning the customer's actual computed figures never appeared anywhere
in the dialog. Found while fixing #285.
"""

import pytest

from cbpos.core.models import Customer
from cbpos.i18n import _t
from cbpos.ui.dialogs.customer_statement_dialog import CustomerStatementDialog

pytestmark = pytest.mark.usefixtures("qapp")

_counter = 0


def _next_suffix() -> str:
    global _counter
    _counter += 1
    return str(_counter)


def _make_customer(db_session):
    customer = Customer(name="Test Customer", phone=f"077{_next_suffix()}")
    db_session.add(customer)
    db_session.flush()
    return customer


class TestSummaryTemplatesHaveAValuePlaceholder:
    def test_each_template_actually_substitutes_the_value(self):
        for key in ("opening", "sales", "payments", "closing"):
            rendered = _t(f"customer_statement.{key}", value="Rs. 123.45")
            assert "Rs. 123.45" in rendered


class TestDialogShowsRealFigures:
    def test_opening_balance_label_shows_a_currency_value_not_just_the_label(self, db_session):
        dialog = CustomerStatementDialog(_make_customer(db_session))
        assert any(ch.isdigit() for ch in dialog.lbl_opening.text())
