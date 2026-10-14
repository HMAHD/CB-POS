"""Shift report builder -- the Z-Report at shift close and the mid-shift X-Read (#682)."""

from decimal import Decimal
from typing import Any

from cbpos.core.services.base_receipt_builder import BaseReceiptBuilder
from cbpos.core.utils.formatters import format_currency


class ShiftReportBuilder(BaseReceiptBuilder):
    """Builds receipt commands for a shift summary from ``ShiftService``.

    Same command format as every other receipt, so it prints through the
    shared PrintWorker and Sinhala/Tamil labels print as images.
    """

    @classmethod
    def build_shift_report(
        cls,
        summary: dict[str, Any],
        x_read: bool = False,
        config_override: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Generate the Z-Report (closed shift) or X-Read (open shift) commands.

        Args:
            summary: ``ShiftService.get_shift_summary`` output; for a Z-Report
                the ``close_shift`` output (adds end_time, actual_cash,
                variance, notes).
            x_read: True for a mid-shift X-Read -- no counted cash or variance.
            config_override: Optional dictionary to override ConfigService values.
        """
        cls._resolve_receipt_lang(config_override)
        commands: list[dict[str, Any]] = []
        line_chars = cls._append_header_block(commands, config_override)

        def sep() -> None:
            commands.append({"type": "text", "val": "-" * line_chars, "align": "center"})

        def heading(key: str) -> None:
            commands.append({"type": "text", "val": cls._rt(key), "align": "left", "bold": True})

        def money_row(key: str, value: Any, bold: bool = False) -> None:
            commands.append(cls._split_row(cls._rt(key), format_currency(value or Decimal(0)), line_chars, bold=bold))

        def time_row(key: str, value: Any) -> None:
            if value:
                commands.append(cls._split_row(cls._rt(key), value.strftime("%Y-%m-%d %H:%M"), line_chars))

        sep()
        title = cls._rt("x_read_title") if x_read else cls._rt("z_report_title")
        commands.append({"type": "text", "val": title, "align": "center", "bold": True})
        sep()

        # Shift info
        commands.append(cls._split_row(cls._rt("cashier"), str(summary.get("user_name") or ""), line_chars))
        commands.append(cls._split_row(cls._rt("shift_id"), str(summary.get("shift_id") or ""), line_chars))
        time_row("shift_start", summary.get("start_time"))
        if not x_read:
            time_row("shift_end", summary.get("end_time"))
        sep()

        # Sales by payment method
        heading("sales_by_method")
        for method, amount in (summary.get("sales_by_method") or {}).items():
            commands.append(cls._split_row(str(method).upper(), format_currency(amount), line_chars))
        money_row("total_sales", summary.get("total_sales"), bold=True)
        sep()

        # Cash control
        heading("cash_control")
        money_row("opening_float", summary.get("starting_cash"))
        money_row("cash_sales", summary.get("cash_sales"))
        money_row("cash_in", summary.get("cash_in"))
        money_row("cash_out", summary.get("cash_out"))
        money_row("expected_cash", summary.get("expected_cash"), bold=True)
        if not x_read:
            money_row("counted_cash", summary.get("actual_cash"))
            money_row("variance", summary.get("variance"), bold=True)
            notes = summary.get("notes")
            if notes:
                for line in cls._wrap_free_text(cls._rt("notes", notes=notes), line_chars):
                    commands.append({"type": "text", "val": line, "align": "left"})
        sep()

        # Audit
        heading("audit")
        commands.append(cls._split_row(cls._rt("txn_count"), str(summary.get("txn_count") or 0), line_chars))
        commands.append(cls._split_row(cls._rt("void_count"), str(summary.get("void_count") or 0), line_chars))
        money_row("void_value", summary.get("void_value"))
        sep()
        commands.append({"type": "text", "val": cls._rt("end_of_report"), "align": "center"})

        cls._append_branding(commands)
        cls._append_cut(commands, config_override)
        return commands
