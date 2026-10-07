from cbpos.core.services.config_service import ConfigService


class ReceiptService:
    """
    Generates the shift Z-Report text.

    Sale, refund and reprint receipts are NOT built here: they all go
    through ``ReceiptBuilder`` via ``PrinterService`` (#625).
    """

    WIDTH_CHARS = 42  # Standard 80mm thermal printer width

    _ROW_FMT = "{:<20} {:>21}"

    @staticmethod
    def _center(text: str) -> str:
        return text.center(ReceiptService.WIDTH_CHARS)

    @staticmethod
    def print_z_report(summary: dict) -> str:
        """
        Generate Z-Report text.
        """
        settings = ConfigService.get_all()
        lines = []

        # 1. Header
        lines.append(ReceiptService._center("Z-REPORT (End of Day)"))
        lines.append(ReceiptService._center(settings.get("shop_name", "CB POS")))
        lines.append("-" * ReceiptService.WIDTH_CHARS)

        # 2. Shift Info
        lines.append(f"User: {summary.get('user_name', 'Unknown')}")
        start_time = summary.get("start_time")
        if start_time:
            lines.append(f"Start: {start_time.strftime('%Y-%m-%d %H:%M')}")
        end_time = summary.get("end_time")
        if end_time:
            lines.append(f"End: {end_time.strftime('%Y-%m-%d %H:%M')}")
        lines.append(f"Shift ID: {summary.get('shift_id')}")
        lines.append("-" * ReceiptService.WIDTH_CHARS)

        # 3. Sales Breakdown
        lines.append("SALES BREAKDOWN")
        lines.append(ReceiptService._ROW_FMT.format("Method", "Amount"))
        for method, amount in summary.get("sales_by_method", {}).items():
            lines.append(ReceiptService._ROW_FMT.format(method, f"{amount:.2f}"))
        lines.append("-" * ReceiptService.WIDTH_CHARS)
        lines.append(ReceiptService._ROW_FMT.format("TOTAL SALES", "{:.2f}".format(summary.get("total_sales", 0))))
        lines.append("-" * ReceiptService.WIDTH_CHARS)

        # 4. Cash Control
        lines.append("CASH CONTROL")
        lines.append(ReceiptService._ROW_FMT.format("Opening Float", "{:.2f}".format(summary.get("starting_cash", 0))))
        lines.append(ReceiptService._ROW_FMT.format("Cash Sales", "{:.2f}".format(summary.get("cash_sales", 0))))
        lines.append(ReceiptService._ROW_FMT.format("Cash In", "{:.2f}".format(summary.get("cash_in", 0))))
        lines.append(ReceiptService._ROW_FMT.format("Cash Out", "{:.2f}".format(summary.get("cash_out", 0))))
        lines.append("-" * ReceiptService.WIDTH_CHARS)
        lines.append(ReceiptService._ROW_FMT.format("Expected Cash", "{:.2f}".format(summary.get("expected_cash", 0))))
        lines.append(ReceiptService._ROW_FMT.format("Actual Cash", "{:.2f}".format(summary.get("actual_cash", 0))))

        variance = summary.get("variance", 0)
        var_label = "VARIANCE"
        lines.append(ReceiptService._ROW_FMT.format(var_label, f"{variance:.2f}"))
        if summary.get("notes"):
            lines.append(f"Note: {summary['notes']}")

        lines.append("-" * ReceiptService.WIDTH_CHARS)

        # 5. Audit
        lines.append("AUDIT")
        lines.append(ReceiptService._ROW_FMT.format("Transactions", str(summary.get("txn_count", 0))))
        lines.append(ReceiptService._ROW_FMT.format("Void Count", str(summary.get("void_count", 0))))
        lines.append(ReceiptService._ROW_FMT.format("Void Value", "{:.2f}".format(summary.get("void_value", 0))))

        lines.append("-" * ReceiptService.WIDTH_CHARS)
        lines.append(ReceiptService._center("*** END OF REPORT ***"))
        lines.append("")
        lines.append(ReceiptService._center("Powered by CB POS"))
        lines.append(ReceiptService._center("ceybyte.com"))
        lines.append("\n\n")

        return "\n".join(lines)
