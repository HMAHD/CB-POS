"""Utility to convert numeric amounts to words for tax invoice compliance.

Supports English (en), Sinhala (si), and Tamil (ta).
Preserves Rupees and Cents ending with 'Only'.
Fails closed for unsupported language codes.
"""

from decimal import Decimal

# --- English Number Dictionaries ---
_ONES_EN = [
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

_TENS_EN = [
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

_SCALES_EN = [
    (10**7, "Crore"),
    (10**5, "Lakh"),
    (10**3, "Thousand"),
    (10**2, "Hundred"),
]


def _two_digit_words_en(n: int) -> str:
    """Convert a number 0-99 to English words."""
    if n < 20:
        return _ONES_EN[n]
    ten, one = divmod(n, 10)
    if one:
        return f"{_TENS_EN[ten]} {_ONES_EN[one]}"
    return _TENS_EN[ten]


def _number_to_words_en(n: int) -> str:
    """Convert a non-negative integer to English words (South Asian numbering)."""
    if n == 0:
        return "Zero"

    parts: list[str] = []

    for value, label in _SCALES_EN:
        if n >= value:
            count, n = divmod(n, value)
            if count >= 100:
                parts.append(f"{_number_to_words_en(count)} {label}")
            elif count >= 20:
                parts.append(f"{_two_digit_words_en(count)} {label}")
            else:
                parts.append(f"{_ONES_EN[count]} {label}")

    if n > 0:
        if n < 20:
            parts.append(_ONES_EN[n])
        else:
            parts.append(_two_digit_words_en(n))

    return " ".join(parts)


# --- Sinhala Number Dictionaries ---
_ONES_SI = ["", "එක", "දෙක", "තුන", "හතර", "පහ", "හය", "හත", "අට", "නවය"]
_TEENS_SI = [
    "",
    "එකොළහ",
    "දොළහ",
    "දහතුන",
    "දහහතර",
    "පහළොව",
    "දහසය",
    "දහහත",
    "දහඅට",
    "දහනවය",
]
_TENS_EXACT_SI = ["", "දහය", "විස්ස", "තිහ", "හතළිහ", "පනහ", "හැට", "හැත්තෑව", "අසූව", "අනූව"]
_TENS_COMB_SI = ["", "දස", "විසි", "තිස්", "හතළිස්", "පනස්", "හැට", "හැත්තෑ", "අසූ", "අනූ"]
_HUNDREDS_SI = [
    "",
    "එක්සිය",
    "දෙසිය",
    "තුන්සිය",
    "හාරසිය",
    "පන්සිය",
    "හයසිය",
    "හත්සිය",
    "අටසිය",
    "නවසිය",
]


def _number_to_words_si(n: int) -> str:
    """Convert a non-negative integer to Sinhala words (South Asian numbering)."""
    if n == 0:
        return "බිංදුව"

    parts: list[str] = []
    crore, n = divmod(n, 10000000)
    if crore:
        parts.append(f"{_number_to_words_si(crore)} කෝටි")
    lakh, n = divmod(n, 100000)
    if lakh:
        parts.append(f"{_number_to_words_si(lakh)} ලක්ෂ")
    thousand, n = divmod(n, 1000)
    if thousand:
        t_str = "එක්දහස්" if thousand == 1 else f"{_number_to_words_si(thousand)} දහස්"
        parts.append(t_str)
    hundred, n = divmod(n, 100)
    if hundred:
        parts.append(_HUNDREDS_SI[hundred])

    if n > 0:
        if n < 10:
            parts.append(_ONES_SI[n])
        elif n == 10:
            parts.append("දහය")
        elif n < 20:
            parts.append(_TEENS_SI[n - 10])
        else:
            t, o = divmod(n, 10)
            if o == 0:
                parts.append(_TENS_EXACT_SI[t])
            else:
                parts.append(f"{_TENS_COMB_SI[t]} {_ONES_SI[o]}")

    return " ".join(parts)


# --- Tamil Number Dictionaries ---
_ONES_TA = ["", "ஒன்று", "இரண்டு", "மூன்று", "நான்கு", "ஐந்து", "ஆறு", "ஏழு", "எட்டு", "ஒன்பது"]
_TEENS_TA = [
    "",
    "பதினொன்று",
    "பன்னிரண்டு",
    "பதின்மூன்று",
    "பதினான்கு",
    "பதினைந்து",
    "பதினாறு",
    "பதினேழு",
    "பதினெட்டு",
    "பத்தொன்பது",
]
_TENS_TA = ["", "பத்து", "இருபது", "முப்பது", "நாற்பது", "ஐம்பது", "அறுபது", "எழுபது", "எண்பது", "தொண்ணூறு"]
_TENS_COMB_TA = [
    "",
    "பத்து",
    "இருபத்து",
    "முப்பத்து",
    "நாற்பத்து",
    "ஐம்பத்து",
    "அறுபத்து",
    "எழுபத்து",
    "எண்பத்து",
    "தொண்ணூற்று",
]
_HUNDREDS_TA = ["", "நூறு", "இருநூறு", "முந்நூறு", "நானூறு", "ஐந்நூறு", "அறுநூறு", "எழுநூறு", "எண்ணூறு", "தொள்ளாயிரம்"]
_HUNDREDS_COMB_TA = [
    "",
    "நூற்று",
    "இருநூற்று",
    "முந்நூற்று",
    "நானூற்று",
    "ஐந்நூற்று",
    "அறுநூற்று",
    "எழுநூற்று",
    "எண்ணூற்று",
    "தொள்ளாயிரத்து",
]


def _number_to_words_ta(n: int) -> str:
    """Convert a non-negative integer to Tamil words (South Asian numbering)."""
    if n == 0:
        return "பூஜ்ஜியம்"

    parts: list[str] = []
    crore, n = divmod(n, 10000000)
    if crore:
        parts.append(f"{_number_to_words_ta(crore)} கோடி")
    lakh, n = divmod(n, 100000)
    if lakh:
        parts.append(f"{_number_to_words_ta(lakh)} லட்சம்")
    thousand, n = divmod(n, 1000)
    if thousand:
        t_str = (
            "ஆயிரத்து"
            if thousand == 1 and n > 0
            else ("ஆயிரம்" if thousand == 1 else f"{_number_to_words_ta(thousand)} ஆயிரம்")
        )
        parts.append(t_str)
    hundred, n = divmod(n, 100)
    if hundred:
        parts.append(_HUNDREDS_COMB_TA[hundred] if n > 0 else _HUNDREDS_TA[hundred])

    if n > 0:
        if n < 10:
            parts.append(_ONES_TA[n])
        elif n == 10:
            parts.append("பத்து")
        elif n < 20:
            parts.append(_TEENS_TA[n - 10])
        else:
            t, o = divmod(n, 10)
            if o == 0:
                parts.append(_TENS_TA[t])
            else:
                parts.append(f"{_TENS_COMB_TA[t]} {_ONES_TA[o]}")

    return " ".join(parts)


def amount_to_words(amount: Decimal, language: str = "en") -> str:
    """
    Convert a monetary amount to words for tax invoice compliance.

    Args:
        amount: The monetary amount (Decimal).
        language: Language code - 'en' (English), 'si' (Sinhala), 'ta' (Tamil).

    Returns:
        Human-readable string, e.g. "One Thousand Two Hundred Fifty Rupees and Fifty Cents Only"

    Raises:
        ValueError: If language is not one of ('en', 'si', 'ta').
    """
    lang = (language or "en").lower().strip()
    if lang not in ("en", "si", "ta"):
        raise ValueError(f"Unsupported language for amount to words: {language}")

    from cbpos.core.utils.money import round_money

    is_negative = amount < 0
    amount = abs(round_money(amount))

    whole = int(amount)
    cents = round((amount - whole) * 100)
    if cents >= 100:
        whole += 1
        cents = 0

    if lang == "en":
        prefix = "Negative " if is_negative else ""
        rupees_str = f"{_number_to_words_en(whole)} Rupees"
        cents_str = f" and {_number_to_words_en(cents)} Cents" if cents > 0 else ""
        return f"{prefix}{rupees_str}{cents_str} Only"

    elif lang == "si":
        prefix = "සෘණ " if is_negative else ""
        rupees_words = _number_to_words_si(whole)
        # Suffix with 'යි' for natural spoken/legal currency format
        rupees_str = f"රුපියල් {rupees_words}යි"
        cents_str = f" ශත {_number_to_words_si(cents)}යි" if cents > 0 else ""
        return f"{prefix}{rupees_str}{cents_str} පමණි"

    elif lang == "ta":
        prefix = "எதிர்மறை " if is_negative else ""
        rupees_words = _number_to_words_ta(whole)
        rupees_str = f"ரூபாய் {rupees_words}"
        cents_str = f" மற்றும் {_number_to_words_ta(cents)} சதம்" if cents > 0 else ""
        return f"{prefix}{rupees_str}{cents_str} மட்டும்"
