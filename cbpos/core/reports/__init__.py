from cbpos.core.reports.registry import ReportRegistry
from cbpos.core.reports.definitions.sales_report import DailySalesSummaryReport
from cbpos.core.reports.definitions.inventory_reports import (
    InventoryValuationReport,
    LowStockReport,
)
from cbpos.core.reports.definitions.sales_reports import (
    SalesByCategoryReport,
    CashierPerformanceReport,
)


def register_all_reports():
    """
    Register all standard reports with the ReportRegistry.
    """
    registry = ReportRegistry()

    # Sales
    registry.register(DailySalesSummaryReport)
    registry.register(SalesByCategoryReport)
    registry.register(CashierPerformanceReport)

    # Inventory
    registry.register(InventoryValuationReport)
    registry.register(LowStockReport)
