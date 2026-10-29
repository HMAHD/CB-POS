"""Unit tests for flat InfoCard widget (#543)."""

from PyQt6.QtWidgets import QLabel

from cbpos.ui.widgets.info_card import InfoCard


def test_info_card_flat_without_graphics_effect(qapp):
    card = InfoCard(title="Total Sales", value="Rs. 1,000.00", icon_name="fa5s.chart-line")
    assert card.graphicsEffect() is None
    assert card.objectName() == "InfoCard"


def test_info_card_labels_and_updates(qapp):
    card = InfoCard(title="Invoices", value="15", icon_name="fa5s.receipt")

    val_lbl = card.findChild(QLabel, "InfoCardValue")
    title_lbl = card.findChild(QLabel, "InfoCardTitle")

    assert val_lbl is not None
    assert val_lbl.text() == "15"
    assert title_lbl is not None
    assert title_lbl.text() == "INVOICES"

    card.set_value("25")
    assert val_lbl.text() == "25"

    card.set_title("Total Invoices")
    assert title_lbl.text() == "TOTAL INVOICES"
