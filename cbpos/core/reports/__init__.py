from cbpos.core.reports.definitions.inventory_reports import (
    InventoryValuationReport,
    LowStockReport,
)
from cbpos.core.reports.definitions.sales_report import DailySalesSummaryReport
from cbpos.core.reports.definitions.sales_reports import (
    CashierPerformanceReport,
    SalesByCategoryReport,
)
from cbpos.core.reports.registry import ReportRegistry


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
    from cbpos.core.reports.definitions.cash_flow_report import CashFlowReport
    from cbpos.core.reports.definitions.financial_reports import (
        ProfitLossReport,
        TaxFilingSummaryReport,
        TaxLiabilityReport,
    )

    registry.register(ProfitLossReport)
    registry.register(TaxLiabilityReport)
    registry.register(TaxFilingSummaryReport)
    registry.register(CashFlowReport)

    # Audit
    from cbpos.core.reports.definitions.audit_reports import (
        CashMovementAuditReport,
        StockMovementReport,
    )

    registry.register(StockMovementReport)
    registry.register(CashMovementAuditReport)

    from cbpos.core.reports.definitions.shift_variance_report import ShiftVarianceReport

    registry.register(ShiftVarianceReport)

    # Void/Refund & Payment Method
    from cbpos.core.reports.definitions.void_refund_report import (
        PaymentMethodSummaryReport,
        VoidRefundReport,
    )

    registry.register(VoidRefundReport)
    registry.register(PaymentMethodSummaryReport)

    # Customer Credit
    from cbpos.core.reports.definitions.credit_report import CustomerCreditReport

    registry.register(CustomerCreditReport)

    # Overdue Customers
    from cbpos.core.reports.definitions.overdue_report import OverdueCustomersReport

    registry.register(OverdueCustomersReport)
