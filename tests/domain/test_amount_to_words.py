from decimal import Decimal

import pytest

from cbpos.core.utils.amount_to_words import amount_to_words


def test_zero_amount():
    assert amount_to_words(Decimal("0.00")) == "Zero Rupees Only"
    assert amount_to_words(Decimal("0")) == "Zero Rupees Only"


def test_whole_rupees():
    assert amount_to_words(Decimal("5.00")) == "Five Rupees Only"
    assert amount_to_words(Decimal("100.00")) == "One Hundred Rupees Only"
    assert amount_to_words(Decimal("1200.00")) == "One Thousand Two Hundred Rupees Only"


def test_rupees_and_cents():
    assert amount_to_words(Decimal("1250.50")) == "One Thousand Two Hundred Fifty Rupees and Fifty Cents Only"
    assert amount_to_words(Decimal("100.05")) == "One Hundred Rupees and Five Cents Only"
    assert amount_to_words(Decimal("0.75")) == "Zero Rupees and Seventy Five Cents Only"
    assert amount_to_words(Decimal("0.05")) == "Zero Rupees and Five Cents Only"


def test_south_asian_scales():
    assert amount_to_words(Decimal("100000.00")) == "One Lakh Rupees Only"
    assert amount_to_words(Decimal("10000000.00")) == "One Crore Rupees Only"
    assert (
        amount_to_words(Decimal("15250000.25"))
        == "One Crore Fifty Two Lakh Fifty Thousand Rupees and Twenty Five Cents Only"
    )


def test_negative_amount():
    assert amount_to_words(Decimal("-50.25")) == "Negative Fifty Rupees and Twenty Five Cents Only"
    assert amount_to_words(Decimal("-100.00")) == "Negative One Hundred Rupees Only"


def test_language_si_and_ta():
    # Sinhala and Tamil should return genuine natural language words
    si_words = amount_to_words(Decimal("150.50"), language="si")
    assert "රුපියල්" in si_words
    assert "ශත" in si_words
    assert "පමණි" in si_words

    ta_words = amount_to_words(Decimal("150.50"), language="ta")
    assert "ரூபாய்" in ta_words
    assert "சதம்" in ta_words
    assert "மட்டும்" in ta_words


def test_unsupported_language_fails_closed():
    # Unsupported language codes must raise ValueError rather than falling back to English
    with pytest.raises(ValueError, match="Unsupported language"):
        amount_to_words(Decimal("150.50"), language="fr")
