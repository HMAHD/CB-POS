"""Pure barcode utilities: symbology selection, module counts, and paper width scaling.

Free of Qt and printer-driver dependencies so core domain and headless services
can safely calculate barcode dimensions (#734, #840, #878).
"""

from cbpos.core.utils.thermal_image import PAPER_DOT_WIDTH


def is_valid_ean13(code: str) -> bool:
    """Check if code is a valid 13-digit EAN-13 string with correct check digit."""
    if not (isinstance(code, str) and len(code) == 13 and code.isdigit()):
        return False
    digits = [int(d) for d in code]
    checksum = sum(digits[i] for i in range(0, 12, 2)) + sum(digits[i] * 3 for i in range(1, 12, 2))
    check_digit = (10 - (checksum % 10)) % 10
    return digits[12] == check_digit


def choose_barcode(data: str | None) -> tuple[str, str]:
    """Select the optimal barcode symbology and payload format for python-escpos.

    - Valid EAN-13 (13 digits with valid checksum) -> ("EAN13", data)
    - Even-length all-digit non-EAN -> ("CODE128", "{C" + data)
    - Other valid data -> ("CODE128", "{B" + data)
    """
    s = str(data or "").strip()
    if s.startswith(("{A", "{B", "{C")):
        return "CODE128", s
    if is_valid_ean13(s):
        return "EAN13", s
    if s.isdigit() and len(s) % 2 == 0 and len(s) > 0:
        return "CODE128", "{C" + s
    return "CODE128", "{B" + s


def code128_module_count(data: str) -> int:
    """Number of modules (dots at width 1) for CODE128 data.

    In Code Set C (pairs of digits), each pair takes 11 modules.
    In Code Set A or B, each character takes 11 modules.
    Formula: 11 * (symbols + 3) + 2 (start, check, stop, plus 2-module terminator).
    """
    s = str(data or "").strip()
    is_c = False
    if s.startswith("{C"):
        clean = s[2:].rstrip("}")
        if clean.isdigit() and len(clean) % 2 == 0:
            is_c = True
    elif s.startswith(("{A", "{B")):
        clean = s[2:].rstrip("}")
    else:
        clean = s
        if clean.isdigit() and len(clean) % 2 == 0 and len(clean) > 0:
            is_c = True
    symbols = (len(clean) // 2) if is_c else len(clean)
    return 11 * (symbols + 3) + 2


def calculate_barcode_width(data: str, paper_width: str = "80mm") -> int | None:
    """Calculate the module width multiplier (1..3) so CODE128 fits on paper.

    Returns None if even width 1 does not fit within PAPER_DOT_WIDTH.
    """
    max_dots = PAPER_DOT_WIDTH.get(paper_width, PAPER_DOT_WIDTH["80mm"])
    modules = code128_module_count(data)
    if modules > max_dots:
        return None
    return max(1, min(3, max_dots // modules))
