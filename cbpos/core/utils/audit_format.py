"""Activity Log display formatting (#613).

Audit rows keep their raw action codes and JSON details in the database; they are turned
into translated, readable text only when shown.
"""

import json
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from cbpos.core.utils.formatters import format_currency, format_date, format_discount, format_promotion_type
from cbpos.i18n import _t

# Keys a {"key": {"old": x, "new": y}} detail can hold -> i18n template key (percent values)
_PERCENT_DETAIL_KEYS = {
    "tax_vat_rate": "audit.detail.tax_vat_rate",
    "tax_sscl_rate": "audit.detail.tax_sscl_rate",
    "tax_sscl_turnover_pct": "audit.detail.tax_sscl_turnover_pct",
}


def _t_or(key: str, fallback: str) -> str:
    text = _t(key)
    return fallback if text == key else text


def format_audit_action(action: str | None) -> str:
    """Translated action label ("TAX_RATE_CHANGE", "User Login", ...); unknown actions as stored."""
    if not action:
        return ""
    return _t_or(f"audit.action.{action.strip().lower().replace(' ', '_')}", action)


def _number(value: Any) -> str:
    """18.0 -> "18", 2.50 -> "2.5"; non-numbers as str."""
    try:
        d = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return str(value)
    return format(d.normalize(), "f")


def _change_text(key: str, old: Any, new: Any) -> str:
    if key == "vat_registered":
        return _t("audit.detail.vat_registered_on" if new else "audit.detail.vat_registered_off")
    if key in _PERCENT_DETAIL_KEYS:
        return _t(_PERCENT_DETAIL_KEYS[key], old=_number(old), new=_number(new))
    return _t("audit.detail.generic", setting=key, old=old, new=new)


# Field of a {"subject", "changes"} detail (#642) -> i18n label key
_FIELD_KEYS = {
    "name": "audit.field.name",
    "start_date": "audit.field.start_date",
    "end_date": "audit.field.end_date",
    "start_time": "audit.field.start_time",
    "end_time": "audit.field.end_time",
    "price": "audit.field.price",
    "type": "audit.field.type",
    "value": "audit.field.value",
    "days_of_week": "audit.field.days_of_week",
    "category": "audit.field.category",
}

# Promotion days are stored as "0,1,2" (0 = Monday)
_DAY_KEYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")


def _is_change(value: Any) -> bool:
    return isinstance(value, dict) and {"old", "new"} <= value.keys()


def _datetime_text(value: Any) -> str:
    try:
        moment = datetime.fromisoformat(str(value))
    except ValueError:
        return str(value)
    text = format_date(moment)
    return text if (moment.hour, moment.minute) == (0, 0) else f"{text} {moment:%H:%M}"


def _days_text(value: Any) -> str:
    days = []
    for part in str(value).split(","):
        part = part.strip()
        days.append(_t(f"promotion.day_{_DAY_KEYS[int(part)]}") if part.isdigit() and int(part) < 7 else part)
    return ", ".join(days)


def _field_value(field: str, value: Any, data: dict) -> str:
    """One stored value as people read it: money, dates, day names, translated types."""
    if field == "days_of_week":
        return _days_text(value) if value else _t("promotion.quick_all")
    if field == "category":
        return str(value) if value else _t("promotion.scope_all_products")
    if field == "price":
        return format_currency(value)
    if field == "value":
        return format_discount(data.get("value_type"), value)
    if field == "type":
        return format_promotion_type(value)
    if field in ("start_date", "end_date", "start_time", "end_time"):
        return _datetime_text(value)
    return str(value)


def _field_change_text(action: str, field: str, old: Any, new: Any, data: dict) -> str | None:
    """One field change as a sentence; None when it adds nothing (the name on a create/delete)."""
    action = (action or "").upper()
    created, deleted = action.endswith("_CREATE"), action.endswith("_DELETE")
    if field == "name" and (created or deleted):
        return None  # already shown as the subject
    if field == "is_active":
        return _t("audit.detail.turned_on" if new else "audit.detail.turned_off")
    if field == "item_count":
        return _t("audit.detail.item_prices_removed", count=old) if old else None
    label = _t_or(_FIELD_KEYS[field], field) if field in _FIELD_KEYS else field
    if created or deleted:
        # A new or deleted record: list what it held, "Type: Percentage"
        return _t("audit.detail.field_value", field=label, value=_field_value(field, old if deleted else new, data))
    # None means "every day" / "all products" for these two, not "nothing"
    if old is None and field not in ("days_of_week", "category"):
        return _t("audit.detail.field_set", field=label, new=_field_value(field, new, data))
    if new is None and field not in ("days_of_week", "category"):
        return _t("audit.detail.field_removed", field=label, old=_field_value(field, old, data))
    return _t(
        "audit.detail.field_changed",
        field=label,
        old=_field_value(field, old, data),
        new=_field_value(field, new, data),
    )


def _subject_change_text(action: str | None, data: dict) -> str:
    """{"subject", "item"?, "changes"} -> "Wholesale / Sugar 1kg: Price changed from Rs. 100.00 to Rs. 95.00"."""
    subject = str(data["subject"])
    if data.get("item"):
        subject = f"{subject} / {data['item']}"
    parts = [
        text
        for field, change in data["changes"].items()
        if (text := _field_change_text(action, field, change["old"], change["new"], data))
    ]
    return f"{subject}: {'; '.join(parts)}" if parts else subject


def format_audit_details(action: str | None, details: str | None) -> str:
    """Readable details: JSON {key: {old, new}} or {"subject", "changes"} becomes sentences.

    Plain text is shown as stored.
    """
    if not details:
        return ""
    try:
        data = json.loads(details)
    except (ValueError, TypeError):
        return details
    if not isinstance(data, dict):
        return details
    if "subject" in data and isinstance(data.get("changes"), dict) and all(map(_is_change, data["changes"].values())):
        return _subject_change_text(action, data)
    if not all(_is_change(v) for v in data.values()):
        return details
    return "; ".join(_change_text(key, change["old"], change["new"]) for key, change in data.items())


def format_log_time(timestamp: datetime | None) -> str:
    """Local "YYYY-MM-DD HH:MM:SS".

    AuditLog.timestamp is written with datetime.now (naive local time), so naive values are
    already local; timezone-aware values are converted to this machine's local time.
    """
    if timestamp is None:
        return ""
    if timestamp.tzinfo is not None:
        timestamp = timestamp.astimezone()
    return timestamp.strftime("%Y-%m-%d %H:%M:%S")
