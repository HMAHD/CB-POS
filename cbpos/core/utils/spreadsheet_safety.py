"""Spreadsheet safety utilities to prevent CSV and formula injection (#898).

Formula injection happens when cell values beginning with '=', '+', '-', '@',
'\t', or '\r' are interpreted as active formulas by spreadsheet programs like
Microsoft Excel, LibreOffice Calc, or Google Sheets.
"""

import math
from typing import Any

# XLSXWriter options to disable auto-converting user strings to formulas or urls.
XLSX_WRITER_OPTIONS = {
    "strings_to_formulas": False,
    "strings_to_urls": False,
}

_DANGEROUS_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def csv_safe(value: Any) -> Any:
    """Sanitize a value for safe CSV export, preventing formula injection.

    If value is a string beginning with '=', '+', '-', '@', '\t', or '\r',
    prefix it with a single quote ('), unless the string parses as a valid
    finite number (e.g. "-150.00"), keeping negative/signed numbers usable.
    """
    if not isinstance(value, str):
        return value

    if not value.startswith(_DANGEROUS_PREFIXES):
        return value

    # Check if the string parses as a valid finite numeric literal
    try:
        val_float = float(value)
        if not math.isnan(val_float) and not math.isinf(val_float):
            return value
    except (ValueError, TypeError):
        pass

    return f"'{value}"
