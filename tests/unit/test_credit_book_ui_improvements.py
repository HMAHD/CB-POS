import re
from decimal import Decimal

import pytest

from cbpos.core.models import Customer
from cbpos.i18n import set_language
from cbpos.ui.views.credit_book_view import CreditBookView

pytestmark = pytest.mark.usefixtures("qapp")

EMOJI_PATTERN = re.compile(r"[\U00010000-\U0010ffff\u2600-\u26FF\u2700-\u27BF]")


def test_customer_metadata_has_no_emojis(db_session):
    customer = Customer(
        name="Test Customer",
        phone="0771234567",
        address="123 Main Street",
        company_name="Acme Corp",
        current_debt=Decimal("1500.00"),
        credit_limit=Decimal("5000.00"),
    )
    db_session.add(customer)
    db_session.flush()

    view = CreditBookView()
    try:
        view.update_header(customer)

        # Phone, Address, Company labels must NOT have any emojis
        assert not EMOJI_PATTERN.search(view.lbl_cust_phone.text())
        assert not EMOJI_PATTERN.search(view.lbl_cust_address.text())
        assert not EMOJI_PATTERN.search(view.lbl_cust_tier.text())

        assert "0771234567" in view.lbl_cust_phone.text()
        assert "123 Main Street" in view.lbl_cust_address.text()
        assert "Acme Corp" in view.lbl_cust_tier.text()

        # Check FontAwesome icons are set
        assert not view.lbl_phone_icon.pixmap().isNull()
        assert not view.lbl_address_icon.pixmap().isNull()
        assert not view.lbl_company_icon.pixmap().isNull()

        # Check visibility (not explicitly hidden)
        assert not view.item_phone.isHidden()
        assert not view.item_address.isHidden()
        assert not view.item_company.isHidden()
    finally:
        view.deleteLater()


def test_back_button_has_no_text_arrow(db_session):
    view = CreditBookView()
    try:
        # In English
        set_language("en")
        view.retranslate_ui()
        assert "<" not in view.btn_back.text()
        assert "Back to Customers" in view.btn_back.text()

        # In Sinhala
        set_language("si")
        view.retranslate_ui()
        assert "<" not in view.btn_back.text()

        # In Tamil
        set_language("ta")
        view.retranslate_ui()
        assert "<" not in view.btn_back.text()
    finally:
        set_language("en")
        view.deleteLater()


def test_button_icons_have_spacing_padding(db_session):
    view = CreditBookView()
    try:
        # Each action button and back button must have an icon whose width is padded (width > height)
        buttons = [
            view.btn_back,
            view.btn_receive_payment,
            view.btn_print_statement,
            view.btn_adjust,
            view.btn_adjust_points,
            view.btn_edit_customer,
        ]
        for btn in buttons:
            icon_size = btn.iconSize()
            assert icon_size.width() > icon_size.height(), f"{btn.objectName()} icon has no trailing padding"
            assert icon_size.width() - icon_size.height() == 8, f"{btn.objectName()} gap is not 8px"
    finally:
        view.deleteLater()


def test_translations_resolve_all_new_keys(db_session):
    for lang in ["en", "si", "ta"]:
        set_language(lang)
        view = CreditBookView()
        try:
            view.retranslate_ui()
            # None of the labels or buttons should show the raw key
            assert "credit_book.view_badge" not in view.lbl_view_badge.text()
            assert "credit_book.preset_30d" not in view.btn_preset_30d.text()
            assert "credit_book.preset_month" not in view.btn_preset_month.text()
            assert "credit_book.kpi_debt" not in view.lbl_kpi_debt_title.text()
            assert "credit_book.kpi_available" not in view.lbl_kpi_avail_title.text()
            assert "credit_book.kpi_limit" not in view.lbl_kpi_limit_title.text()
            assert "credit_book.kpi_points" not in view.lbl_kpi_points_title.text()
            assert "credit_book.kpi_last_payment" not in view.lbl_kpi_last_title.text()
        finally:
            view.deleteLater()
    set_language("en")


def test_metadata_containers_have_meta_container_object_name(db_session):
    view = CreditBookView()
    try:
        assert view.item_phone.objectName() == "MetaContainer"
        assert view.item_address.objectName() == "MetaContainer"
        assert view.item_company.objectName() == "MetaContainer"
    finally:
        view.deleteLater()


def test_qss_has_scoped_meta_container_rules():
    from pathlib import Path

    style_dir = Path(__file__).parent.parent.parent / "cbpos" / "ui" / "styles"
    dark_qss = (style_dir / "dark.qss").read_text()
    light_qss = (style_dir / "light.qss").read_text()
    assert "QFrame#CreditHeaderCard QWidget#MetaContainer" in dark_qss
    assert "QFrame#CreditHeaderCard QWidget#MetaContainer" in light_qss
    assert "QFrame#CreditHeaderCard QWidget {" not in dark_qss
    assert "QFrame#CreditHeaderCard QWidget {" not in light_qss


def test_search_and_add_button_in_same_toolbar(db_session):
    from PyQt6.QtCore import Qt

    view = CreditBookView()
    try:
        # Search input and Add Customer button should be in the same horizontal layout
        assert view.btn_add_customer.parentWidget() == view.search_input.parentWidget()
        assert view.search_input.isClearButtonEnabled()
        assert view.btn_add_customer.cursor().shape() == Qt.CursorShape.PointingHandCursor
    finally:
        view.deleteLater()
