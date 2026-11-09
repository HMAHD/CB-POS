"""Customer statement receipt builder — generates receipt commands for credit statements."""

from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from cbpos.core.services.base_receipt_builder import BaseReceiptBuilder
from cbpos.core.utils.formatters import format_currency
from cbpos.i18n import translate_in

if TYPE_CHECKING:
    from cbpos.core.models import Customer, CustomerLedgerEntry


class StatementReceiptBuilder(BaseReceiptBuilder):
    """Builds receipt commands for customer credit statements."""

    @classmethod
    def build_customer_statement(
        cls,
        customer: "Customer",
        entries: list["CustomerLedgerEntry"],
        period_from: datetime,
        period_to: datetime,
        config_override: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
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
        commands: list[dict[str, Any]] = []

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
        if isinstance(period_to, datetime):
            if period_to.time() == time.min and period_to > period_from:
                to_date = (period_to - timedelta(days=1)).date()
            else:
                to_date = period_to.date()
        elif isinstance(period_to, date):
            to_date = period_to
        else:
            to_date = period_to
        to_str = to_date.strftime("%Y-%m-%d")

        period_text = translate_in(
            cls._receipt_lang or "en",
            "statement.period_range",
            **{"from": from_str, "to": to_str},
        )
        commands.append({"type": "text", "val": f"{cls._rt('period')}: {period_text}", "align": "left"})
        commands.append({"type": "text", "val": "-" * line_chars, "align": "center"})

        # Opening Balance
        if entries:
            opening = entries[0].balance_after - entries[0].amount
        else:
            from cbpos.core.services.customer_credit_service import CustomerCreditService

            opening = CustomerCreditService.balance_at(customer.id, period_from)

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
                line = f"{date_str} {doc:<20} +{entry.amount:.2f}"
                total_debit += entry.amount
            else:
                line = f"{date_str} {doc:<20} {entry.amount:.2f}"
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
        closing = entries[-1].balance_after if entries else opening
        commands.append({"type": "feed", "lines": 1})
        commands.append(
            {"type": "text", "val": f"{cls._rt('closing_balance')}: {format_currency(closing)}", "align": "right"}
        )

        # Footer
        commands.append({"type": "feed", "lines": 1})
        commands.append({"type": "text", "val": cls._rt("thank_you"), "align": "center"})

        cls._append_footer_text(commands, line_chars, config_override)

        cls._append_branding(commands)
        cls._append_cut(commands, config_override)

        return commands
