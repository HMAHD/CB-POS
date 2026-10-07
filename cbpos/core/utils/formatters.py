from datetime import date, datetime
from decimal import Decimal
from typing import Union

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


def format_currency(value: Union[Decimal, float, int, str]) -> str:
    """
    Format a monetary value using the configured currency symbol.
    Example: "Rs. 1,250.00" or "$ 10.50"
    """
    if value is None:
        return ""

    try:
        d_value = Decimal(str(value))
    except Exception:
        return str(value)

    symbol = ConfigService.get("currency_symbol") or "Rs."
    # Format with commas and 2 decimal places
    formatted_number = f"{d_value:,.2f}"
    return f"{symbol} {formatted_number}"


def get_currency_symbol() -> str:
    """Get the configured currency symbol (e.g., 'Rs.' or '$')."""
    return ConfigService.get("currency_symbol") or "Rs."


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
