"""Customer statement receipt builder — generates receipt commands for credit statements."""

from datetime import datetime
from decimal import Decimal
from typing import List, Dict, Any, Optional, TYPE_CHECKING

from cbpos.core.services.base_receipt_builder import BaseReceiptBuilder
from cbpos.core.utils.formatters import format_currency

if TYPE_CHECKING:
    from cbpos.core.models import Customer, CustomerLedgerEntry


class StatementReceiptBuilder(BaseReceiptBuilder):
    """Builds receipt commands for customer credit statements."""

    @classmethod
    def build_customer_statement(
        cls,
        customer: "Customer",
        entries: List["CustomerLedgerEntry"],
        period_from: datetime,
        period_to: datetime,
        config_override: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Generates receipt commands for a customer credit statement.

        Args:
            customer: The Customer model instance.
            entries: List of CustomerLedgerEntry objects.
            period_from: Statement start date.
            period_to: Statement end date.
            config_override: Optional dictionary to override ConfigService values.
        """
        cls._resolve_receipt_lang(config_override)
        commands: List[Dict[str, Any]] = []
        gc = cls._get_conf

        line_chars = cls._append_header_block(commands, config_override)

        # Title
        commands.append({"type": "text", "val": cls._rt("statement"), "align": "center"})
        commands.append({"type": "feed", "lines": 1})

        # Customer Info
        commands.append({"type": "text", "val": f"{cls._rt('customer')}: {customer.name}", "align": "left"})
        if customer.phone:
            commands.append({"type": "text", "val": f"{cls._rt('phone')}: {customer.phone}", "align": "left"})

        # Period
        from_str = period_from.strftime("%Y-%m-%d")
        to_str = period_to.strftime("%Y-%m-%d")
        commands.append({"type": "text", "val": f"{cls._rt('period')}: {from_str} to {to_str}", "align": "left"})
        commands.append({"type": "text", "val": "-" * line_chars, "align": "center"})

        # Opening Balance
        if entries:
            opening = entries[0].balance_after - entries[0].amount
        else:
            opening = customer.current_debt

        commands.append(
            {"type": "text", "val": f"{cls._rt('opening_balance')}: {format_currency(opening)}", "align": "left"}
        )
        commands.append({"type": "text", "val": "-" * line_chars, "align": "center"})

        # Entries
        total_debit = Decimal("0.00")
        total_credit = Decimal("0.00")
        for entry in entries:
            date_str = entry.timestamp.strftime("%m/%d") if entry.timestamp else ""
            doc = entry.reference_doc or entry.note or entry.entry_type

            if entry.amount > 0:
                line = f"{date_str} {doc:<20} +{entry.amount:.2f}"  # noqa: E231
                total_debit += entry.amount
            else:
                line = f"{date_str} {doc:<20} {entry.amount:.2f}"  # noqa: E231
                total_credit += abs(entry.amount)

            commands.append({"type": "text", "val": line, "align": "left"})

        commands.append({"type": "text", "val": "-" * line_chars, "align": "center"})

        # Totals
        commands.append(
            {"type": "text", "val": f"{cls._rt('total_sales')}: {format_currency(total_debit)}", "align": "right"}
        )
        commands.append(
            {"type": "text", "val": f"{cls._rt('total_payments')}: {format_currency(total_credit)}", "align": "right"}
        )

        # Closing Balance
        closing = entries[-1].balance_after if entries else customer.current_debt
        commands.append({"type": "feed", "lines": 1})
        commands.append(
            {"type": "text", "val": f"{cls._rt('closing_balance')}: {format_currency(closing)}", "align": "right"}
        )

        # Footer
        commands.append({"type": "feed", "lines": 1})
        commands.append({"type": "text", "val": cls._rt("thank_you"), "align": "center"})

        footer_text = gc("receipt_footer", "", config_override)
        if footer_text:
            commands.append({"type": "feed", "lines": 1})
            commands.append({"type": "text", "val": footer_text, "align": "center"})

        cls._append_branding(commands)
        cls._append_cut(commands, config_override)

        return commands
