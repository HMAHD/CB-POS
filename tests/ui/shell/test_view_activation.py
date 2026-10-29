"""Management views reload when shown again (view lifecycle contract, D16).

Views are created once and cached. Before the contract, data added while a
view was hidden (a supplier added from another till, a GRN, a sale) stayed
invisible until the user pressed Refresh.
"""

import pytest

from cbpos.core.services.supplier_service import SupplierService
from cbpos.ui.components.activation import Activatable
from cbpos.ui.views.dashboard_view import DashboardView
from cbpos.ui.views.management_view import ManagementView

pytestmark = pytest.mark.usefixtures("qapp")

PURCHASING, INVENTORY = 2, 1


def _supplier_names(view: ManagementView) -> list[str]:
    model = view.purchase_view.supplier_table.model()
    return (
        [s.company_name for s in model._suppliers]
        if hasattr(model, "_suppliers")
        else [model.index(r, 1).data() for r in range(model.rowCount())]
    )


def test_supplier_added_while_hidden_shows_when_purchasing_is_reopened(db_session):
    view = ManagementView()
    view.switch_tab(PURCHASING)
    view.switch_tab(INVENTORY)

    SupplierService.create_supplier("Lanka Activation Traders")
    view.switch_tab(PURCHASING)

    assert "Lanka Activation Traders" in _supplier_names(view)


def test_every_cached_management_view_takes_part_in_the_lifecycle(db_session):
    view = ManagementView()
    for index in view._view_attr_names:
        widget = view._get_or_create_view(index)
        # The dashboard reloads in its own showEvent; reports load on demand.
        if isinstance(widget, DashboardView) or view._view_attr_names[index] == "reports_view":
            continue
        assert isinstance(widget, Activatable), f"{type(widget).__name__} must mix in Activatable"
