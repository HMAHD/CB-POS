"""
Refund confirm/done wording shared by every refund entry point (#715).

A refund of a credit sale takes the credit part off the customer's debt, so
only the rest is handed back. Each screen used to say "Refund of {full
total}", which told the cashier to hand the whole amount back -- paying a
credit sale back twice. These helpers spell out both parts instead, from
``TransactionService.refund_breakdown``.
"""

import html

from cbpos.core.services.refund_breakdown import RefundBreakdown
from cbpos.core.utils.formatters import format_currency
from cbpos.i18n import _t


def refund_split_lines(breakdown: RefundBreakdown, done: bool = False) -> list[str]:
    """What the cashier hands back and what comes off the customer's credit.

    Only non-zero parts are listed; an all-credit sale says there is nothing
    to hand back.

    Args:
        breakdown: Result of ``TransactionService.refund_breakdown``.
        done: True for the after-the-refund message (past tense for credit).

    Returns:
        Translated lines, in display order.
    """
    cash_back = breakdown.cash_back
    credit = breakdown.credit_reversed
    lines: list[str] = []
    if cash_back > 0:
        lines.append(_t("refund_split.cash_back", amount=format_currency(cash_back)))
    elif credit > 0:
        lines.append(_t("refund_split.nothing_to_hand_back"))
    if credit > 0:
        key = "refund_split.credit_reversed" if done else "refund_split.credit_will_reverse"
        customer = breakdown.customer_name or _t("refund.walk_in")
        lines.append(_t(key, amount=format_currency(credit), customer=customer))
    return lines


def refund_confirm_text(doc_number: str, breakdown: RefundBreakdown, reason: str = "") -> str:
    """Plain-text confirmation: the question, the split, then the reason if any.

    Args:
        doc_number: Receipt number of the sale being refunded.
        breakdown: Result of ``TransactionService.refund_breakdown``.
        reason: Refund reason typed by the cashier, shown last.

    Returns:
        Message text for a QMessageBox.
    """
    parts = [_t("refund_split.confirm_question", doc_number=doc_number, amount=format_currency(breakdown.total))]
    parts.append("\n".join(refund_split_lines(breakdown)))
    if reason:
        parts.append(_t("refund_split.reason", reason=reason))
    return "\n\n".join(p for p in parts if p)


def refund_done_text(doc_number: str, breakdown: RefundBreakdown) -> str:
    """Plain-text success message: refund done, then the split.

    Args:
        doc_number: Receipt number of the refunded sale.
        breakdown: Result of ``TransactionService.refund_breakdown`` taken before the refund.

    Returns:
        Message text for a QMessageBox.
    """
    lines = refund_split_lines(breakdown, done=True)
    return "\n\n".join([_t("refund_split.done", doc_number=doc_number), "\n".join(lines)]).strip()


def refund_confirm_html(
    doc_number: str, breakdown: RefundBreakdown, *, question: str, receipt_label: str, warning: str
) -> str:
    """Rich-text confirmation for screens that show the refund as a bold question with a warning.

    The receipt number and the split are escaped; the screen's own translated
    ``question``, ``receipt_label`` and ``warning`` are used as given.

    Args:
        doc_number: Receipt number of the sale being refunded.
        breakdown: Result of ``TransactionService.refund_breakdown``.
        question: Bold heading, e.g. "Refund Transaction?".
        receipt_label: Label for the receipt number line.
        warning: Text after the red "Warning:" at the end.

    Returns:
        HTML for a rich-text QMessageBox.
    """
    return (
        f"<b>{question}</b><br><br>"
        f"{receipt_label}: {html.escape(doc_number)}<br>"
        f"{_t('common.amount')}: {format_currency(breakdown.total)}<br><br>"
        f"{as_html(chr(10).join(refund_split_lines(breakdown)))}<br><br>"
        f"<b style='color: #FF4136'>{_t('common.warning')}:</b> "
        f"{warning}"
    )


def as_html(text: str) -> str:
    """Escape plain text for a rich-text QMessageBox, keeping line breaks."""
    return html.escape(text).replace("\n", "<br>")
