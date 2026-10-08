"""Activity Log display formatting (#613).

Audit rows keep their raw action codes and JSON details in the database; they are turned
into translated, readable text only when shown.
"""

import json
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any

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


def format_audit_details(action: str | None, details: str | None) -> str:
    """Readable details: JSON {key: {old, new}} becomes sentences; plain text is shown as stored."""
    if not details:
        return ""
    try:
        data = json.loads(details)
    except (ValueError, TypeError):
        return details
    if not isinstance(data, dict) or not all(isinstance(v, dict) and {"old", "new"} <= v.keys() for v in data.values()):
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
