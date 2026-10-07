from collections.abc import Callable
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any, Union

from cbpos.core.services.config_service import ConfigService


def format_short_name(full_name: str) -> str:
    """
    Shortens a full name to its first part plus an initial for each
    remaining part, for display in space-constrained UI.
    Example: "Nimal Kasun Perera" -> "Nimal K P".
    """
    if not full_name:
        return ""

    parts = full_name.split()
    if len(parts) <= 1:
        return full_name

    initials = " ".join(part[0].upper() for part in parts[1:])
    return f"{parts[0]} {initials}"


def format_bytes(size: int) -> str:
    """
    Human-readable file size: whole KB under 1 MB, one decimal above.
    Examples: 45_000 -> "44 KB", 1_363_149 -> "1.3 MB".

    Never shows a small, non-empty file as "0.0 MB" (#618).
    """
    sign = "-" if size < 0 else ""
    size = abs(size)
    kb = round(size / 1024)
    if size and kb == 0:
        kb = 1
    if kb < 1024:
        return f"{sign}{kb} KB"
    if size < 1024**3:
        return f"{sign}{size / 1024**2:.1f} MB"
    return f"{sign}{size / 1024**3:.1f} GB"


DEFAULT_CURRENCY_SYMBOL = "Rs."

# Shown in a number cell that has no value of its own (e.g. a price list
# row with no override), so "no value" never reads as zero.
NO_VALUE = "\u2014"
# A real minus sign: as wide as "+", unlike the hyphen.
MINUS_SIGN = "\u2212"

# How every number in a table is shown (one rule, every screen):
#   - right-aligned (table_helpers.NUMERIC_ALIGNMENT), header too;
#   - thousands separators via format_number()/format_quantity();
#   - money columns carry the currency symbol once, in the header
#     (money_header()), so cells stay short and line up;
#   - a single amount outside a table uses format_currency().


def _to_decimal(value: Any) -> Decimal | None:
    """Coerce int/float/Decimal/numpy scalar/numeric str to Decimal; None if not a finite number."""
    if value is None or isinstance(value, bool):
        return None
    try:
        d_value = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None
    return d_value if d_value.is_finite() else None


def format_number(value: Any, decimals: int = 2) -> str:
    """Format a number with thousands separators and a fixed number of decimals.

    Accepts int, float, Decimal, numpy scalars (e.g. numpy.int64) and numeric
    strings. Rounds half-up, like money. None/NaN/non-numbers return "" (a
    non-number string is returned unchanged so no data is hidden).

    Examples: format_number(1650) -> "1,650.00", format_number(12345, 0) -> "12,345".
    """
    d_value = _to_decimal(value)
    if d_value is None:
        return "" if value is None or not isinstance(value, str) else value
    rounded = d_value.quantize(Decimal(1).scaleb(-decimals), rounding=ROUND_HALF_UP)
    if rounded == 0:
        rounded = abs(rounded)  # never "-0.00"
    return f"{rounded:,.{decimals}f}"


def quantity_decimals(unit: Any) -> int:
    """Decimal places a quantity is shown with: the unit's own, else 3.

    ``unit`` may be a Unit (uses ``decimal_places``), a plain int, or None
    (unknown unit: full 3-decimal precision so nothing is hidden).
    """
    if isinstance(unit, int) and not isinstance(unit, bool):
        places = unit
    elif unit is not None and getattr(unit, "decimal_places", None) is not None:
        places = unit.decimal_places
    else:
        places = 3
    return max(0, min(int(places), 3))


def format_quantity(value: Any, unit: Any = None) -> str:
    """Format a stock quantity with the unit's decimal places and separators.

    A piece unit (0 decimals) shows ``12``, a kg unit (3 decimals) ``1.250``.
    If the value carries more precision than its unit allows (bad data),
    up to 3 decimals are shown rather than silently rounding it away.
    """
    d_value = _to_decimal(value)
    if d_value is None:
        return format_number(value)
    decimals = quantity_decimals(unit)
    if d_value != d_value.quantize(Decimal(1).scaleb(-decimals), rounding=ROUND_HALF_UP):
        decimals = 3
    return format_number(d_value, decimals)


def format_signed(value: Any, formatter: Callable[[Any], str]) -> str:
    """Prefix ``formatter(abs(value))`` with "+" or a minus sign; zero gets no sign.

    Used for variances, so a surplus and a shortage differ in text, not
    only in colour. Example: format_signed(-2, format_quantity) -> "\u22122.000".
    """
    d_value = _to_decimal(value)
    if d_value is None:
        return formatter(value)
    text = formatter(abs(d_value))
    if d_value > 0 and text != formatter(0):
        return f"+{text}"
    if d_value < 0 and text != formatter(0):
        return f"{MINUS_SIGN}{text}"
    return text


def format_currency(value: Union[Decimal, float, int, str]) -> str:
    """
    Format a monetary value using the configured currency symbol.
    Example: "Rs. 1,250.00" or "$ 10.50"
    """
    if value is None:
        return ""

    if _to_decimal(value) is None:
        return str(value)

    return f"{get_currency_symbol()} {format_number(value, 2)}"


def get_currency_symbol() -> str:
    """Get the configured currency symbol (e.g., 'Rs.' or '$')."""
    return ConfigService.get("currency_symbol") or DEFAULT_CURRENCY_SYMBOL


def money_header(label: str) -> str:
    """A money column's header with the currency symbol: "Price" -> "Price (Rs.)"."""
    return f"{label} ({get_currency_symbol()})"


def format_discount(kind: str | None, value: Any) -> str:
    """Show a discount by its kind: "10%" for a percentage, "Rs. 50.00" for a fixed amount.

    ``kind`` is a sale-line discount type (PERCENTAGE/PERCENT, FIXED) or a
    promotion type (PERCENTAGE, FIXED_AMOUNT, BOGO). No discount ("NONE"
    or empty) returns ""; a kind with no amount (BOGO) returns NO_VALUE.
    """
    kind = (kind or "NONE").upper()
    if kind == "NONE":
        return ""
    if kind in ("PERCENTAGE", "PERCENT"):
        d_value = _to_decimal(value)
        if d_value is None:
            return NO_VALUE
        decimals = 0 if d_value == d_value.to_integral_value() else 2
        return f"{format_number(d_value, decimals)}%"
    if kind in ("FIXED", "FIXED_AMOUNT", "AMOUNT"):
        return format_currency(value)
    return NO_VALUE


def format_date(date_obj: Union[datetime, date, str]) -> str:
    """
    Format a date object using the configured date format.
    """
    if not date_obj:
        return ""

    if isinstance(date_obj, str):
        # Try to parse if string
        try:
            date_obj = datetime.fromisoformat(date_obj)
        except ValueError:
            return date_obj

    fmt = ConfigService.get("date_format") or "YYYY-MM-DD"

    # Map simple format strings to strftime
    # This is a basic mapping, can be expanded
    strftime_fmt = "%Y-%m-%d"
    if fmt == "DD/MM/YYYY":
        strftime_fmt = "%d/%m/%Y"
    elif fmt == "MM/DD/YYYY":
        strftime_fmt = "%m/%d/%Y"

    try:
        return date_obj.strftime(strftime_fmt)
    except Exception:
        return str(date_obj)


def escape_like(value: str) -> str:
    """
    Escape special characters (%, _, \\) in a value for use in SQL LIKE patterns.
    Prevents user input from being interpreted as LIKE wildcards.
    """
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
