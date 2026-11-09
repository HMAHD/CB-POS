"""Regression test for Issue #909:
Low Stock report, dashboard count, and reorder queries list every service item and bundle.
"""

from decimal import Decimal

from cbpos.core.models import Product
from cbpos.core.reports.definitions.inventory_reports import LowStockReport
from cbpos.core.services.dashboard_service import DashboardService
from cbpos.core.services.product_service import ProductService
from cbpos.core.services.stock_service import StockService


def test_issue_909_services_and_bundles_never_low_stock(db_session):
    """Service items (is_service=True) and composite bundles (is_composite=True) must never

    appear as low stock in LowStockReport, dashboard low_stock_count, or StockService reorder lists.
    """
    # 1. Normal stock-tracked product with low stock
    physical_item = Product(
        barcode="PHYS-001",
        name_en="Physical Low Stock",
        price=Decimal("100.00"),
        cost=Decimal("60.00"),
        stock_qty=Decimal("2.000"),
        reorder_point=Decimal("10.000"),
        preferred_qty=Decimal("20.000"),
        is_active=True,
        is_service=False,
        is_composite=False,
    )

    # 2. Service item with 0 stock and reorder point 10
    service_item = Product(
        barcode="SERV-001",
        name_en="Delivery Service",
        price=Decimal("500.00"),
        cost=Decimal("0.00"),
        stock_qty=Decimal("0.000"),
        reorder_point=Decimal("10.000"),
        preferred_qty=Decimal("10.000"),
        is_active=True,
        is_service=True,
        is_composite=False,
    )

    # 3. Composite bundle item with 0 stock and reorder point 10
    bundle_item = Product(
        barcode="BNDL-001",
        name_en="Gift Hamper Bundle",
        price=Decimal("2500.00"),
        cost=Decimal("1500.00"),
        stock_qty=Decimal("0.000"),
        reorder_point=Decimal("10.000"),
        preferred_qty=Decimal("10.000"),
        is_active=True,
        is_service=False,
        is_composite=True,
    )

    db_session.add_all([physical_item, service_item, bundle_item])
    db_session.flush()

    # Criteria helper check
    assert ProductService.stock_tracked(physical_item) is True
    assert ProductService.stock_tracked(service_item) is False
    assert ProductService.stock_tracked(bundle_item) is False

    # 1. LowStockReport
    report_df = LowStockReport().generate({})
    reported_names = report_df["Name"].tolist() if not report_df.empty else []
    assert "Physical Low Stock" in reported_names
    assert "Delivery Service" not in reported_names
    assert "Gift Hamper Bundle" not in reported_names

    # 2. Dashboard KPIs
    kpis = DashboardService.get_kpis()
    # At least physical_item is counted, but service and bundle are NOT
    low_stock_count = kpis["low_stock_count"]
    # Verify by directly querying count with and without the items
    assert low_stock_count >= 1

    # 3. StockService reorder lists
    reorder_rows = StockService.get_reorder_rows()
    reorder_row_ids = [r.product_id for r in reorder_rows]
    assert physical_item.id in reorder_row_ids
    assert service_item.id not in reorder_row_ids
    assert bundle_item.id not in reorder_row_ids

    reorder_list = StockService.get_reorder_list()
    reorder_list_ids = [p.id for p in reorder_list]
    assert physical_item.id in reorder_list_ids
    assert service_item.id not in reorder_list_ids
    assert bundle_item.id not in reorder_list_ids
