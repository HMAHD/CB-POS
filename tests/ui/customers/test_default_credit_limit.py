"""Settings -> Sales & Tax -> "Default Credit Limit" ("Default credit limit
for new customers. 0 = no credit.") was saved but never read: every new
customer started at 0 whatever the owner set. A new customer now starts at
the saved default -- prefilled in the New Customer dialog, and applied by
CustomerService when a caller (e.g. Quick Add) gives no limit.
"""

from decimal import Decimal

import pytest

from cbpos.core.models import Customer
from cbpos.core.services.config_service import ConfigService
from cbpos.core.services.customer_service import CustomerService
from cbpos.ui.dialogs.customer_editor import CustomerEditor

pytestmark = pytest.mark.usefixtures("qapp")


@pytest.fixture
def default_limit(monkeypatch):
    real_get = ConfigService.get
    monkeypatch.setattr(
        ConfigService, "get", staticmethod(lambda key: 5000 if key == "default_credit_limit" else real_get(key))
    )
    return Decimal("5000")


def test_quick_add_customer_without_a_limit_gets_the_default(db_session, default_limit):
    customer = CustomerService().create_customer({"name": "Default Limit Quick", "is_active": True})

    assert customer.credit_limit == default_limit


def test_an_explicit_limit_is_kept(db_session, default_limit):
    customer = CustomerService().create_customer({"name": "Default Limit Explicit", "credit_limit": Decimal("0")})

    assert customer.credit_limit == Decimal("0")


def test_new_customer_dialog_is_prefilled_with_the_default(db_session, default_limit):
    dialog = CustomerEditor()

    assert dialog.limit_input.text() == "5000.00"


def test_editing_a_customer_shows_their_own_limit(db_session, default_limit):
    customer = Customer(name="Default Limit Existing", credit_limit=Decimal("750"))
    db_session.add(customer)
    db_session.flush()

    dialog = CustomerEditor(customer=customer)

    assert dialog.limit_input.text() == "750.00"
