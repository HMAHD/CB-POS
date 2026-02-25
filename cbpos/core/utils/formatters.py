from decimal import Decimal
from datetime import datetime, date
from typing import Union
from cbpos.core.services.config_service import ConfigService


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
    formatted_number = "{:,.2f}".format(d_value)
    return f"{symbol} {formatted_number}"


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
