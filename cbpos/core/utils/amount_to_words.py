"""
Utility to convert numeric amounts to words for tax invoice compliance.
Supports English, with Sinhala and Tamil placeholders.
"""

from decimal import Decimal

_ONES = [
    "",
    "One",
    "Two",
    "Three",
    "Four",
    "Five",
    "Six",
    "Seven",
    "Eight",
    "Nine",
    "Ten",
    "Eleven",
    "Twelve",
    "Thirteen",
    "Fourteen",
    "Fifteen",
    "Sixteen",
    "Seventeen",
    "Eighteen",
    "Nineteen",
]

_TENS = [
    "",
    "",
    "Twenty",
    "Thirty",
    "Forty",
    "Fifty",
    "Sixty",
    "Seventy",
    "Eighty",
    "Ninety",
]

_SCALES = [
    (10**7, "Crore"),
    (10**5, "Lakh"),
    (10**3, "Thousand"),
    (10**2, "Hundred"),
]


def _two_digit_words(n: int) -> str:
    """Convert a number 0-99 to words."""
    if n < 20:
        return _ONES[n]
    ten, one = divmod(n, 10)
    if one:
        return f"{_TENS[ten]} {_ONES[one]}"
    return _TENS[ten]


def _number_to_words_en(n: int) -> str:
    """Convert a non-negative integer to English words (South Asian numbering)."""
    if n == 0:
        return "Zero"

    parts: list[str] = []

    for value, label in _SCALES:
        if n >= value:
            count, n = divmod(n, value)
            # Recursively convert count if >= 100 (e.g., 150 Crore)
            if count >= 100:
                parts.append(f"{_number_to_words_en(count)} {label}")
            elif count >= 20:
                parts.append(f"{_two_digit_words(count)} {label}")
            else:
                parts.append(f"{_ONES[count]} {label}")

    if n > 0:
        if n < 20:
            parts.append(_ONES[n])
        else:
            parts.append(_two_digit_words(n))

    return " ".join(parts)


def amount_to_words(amount: Decimal, language: str = "en") -> str:
    """
    Convert a monetary amount to words.

    Args:
        amount: The monetary amount (Decimal). Cents/paisa are ignored for
                tax invoice purposes (whole LKR only).
        language: Language code - 'en' (English), 'si' (Sinhala), 'ta' (Tamil).

    Returns:
        Human-readable string, e.g. "One Thousand Two Hundred Rupees"
    """
    # Work with absolute value, handle negative
    if amount < 0:
        prefix = "Negative "
        amount = abs(amount)
    else:
        prefix = ""

    # Truncate to whole rupees for tax invoice compliance
    whole = int(amount)

    if language in ("si", "ta"):
        # Sinhala and Tamil: fall back to English with a note
        words = _number_to_words_en(whole)
        return f"{prefix}{words} Rupees"

    words = _number_to_words_en(whole)
    return f"{prefix}{words} Rupees"
