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

    # Financial
    from cbpos.core.reports.definitions.financial_reports import (
        ProfitLossReport,
        TaxLiabilityReport,
    )

    registry.register(ProfitLossReport)
    registry.register(TaxLiabilityReport)

    # Audit
    from cbpos.core.reports.definitions.audit_reports import StockMovementReport

    registry.register(StockMovementReport)

    # Void/Refund & Payment Method
    from cbpos.core.reports.definitions.void_refund_report import (
        VoidRefundReport,
        PaymentMethodSummaryReport,
    )

    registry.register(VoidRefundReport)
    registry.register(PaymentMethodSummaryReport)

    # Customer Credit
    from cbpos.core.reports.definitions.credit_report import CustomerCreditReport

    registry.register(CustomerCreditReport)

    # Overdue Customers
    from cbpos.core.reports.definitions.overdue_report import OverdueCustomersReport

    registry.register(OverdueCustomersReport)
