"""
#638: Settings -> Documents saved any number format, so one typo in the
Purchase format stopped GRNs saving. Invalid formats now show a red error
next to the field and block Save; valid ones show a live "Next:" preview.
"""

from datetime import datetime

import pytest

from cbpos.i18n import _t
from cbpos.ui.views.settings_pages import DocumentPage

pytestmark = pytest.mark.usefixtures("qapp")


@pytest.fixture
def page(db_session):
    p = DocumentPage()
    p.load({"terminal_id": "TERM-01", "doc_reset_period": "YEARLY"})
    yield p
    p.deleteLater()


def test_format_without_seq_is_rejected_with_message_next_to_field(page):
    page.input_fmt_purchase.setText("GRN-{Y}")

    with pytest.raises(ValueError):
        page.validate()

    label = page._preview_purchase
    assert label.property("class") == "error"
    assert label.text() != ""
    assert "GRN-" not in label.text()


def test_valid_format_shows_next_number_preview(page):
    page.input_fmt_purchase.setText("GRN-{Y}-{seq:05d}")

    page.validate()  # does not raise

    year = datetime.now().strftime("%Y")
    assert f"GRN-{year}-" in page._preview_purchase.text()
    assert page._preview_purchase.property("class") != "error"


def test_sale_and_return_fields_are_validated_too(page):
    page.input_fmt_sale.setText("INV-{seq}-{Y}")

    with pytest.raises(ValueError):
        page.validate()


def test_sale_and_return_formats_show_next_number(page, monkeypatch):
    """#637: Sale/Return formats now drive real receipt numbers, so they get
    the same "Next:" preview Purchase has (#638 hid it until then)."""
    from cbpos.core.services.config_service import ConfigService

    monkeypatch.setattr(ConfigService, "get", lambda key, default=None: default)
    page.input_fmt_sale.setText("INV-{Y}-{seq:05d}")
    page.input_fmt_return.setText("CN-{Y}-{seq:05d}")

    year = datetime.now().strftime("%Y")
    assert page._preview_sale.text() == _t("settings.documents.fmt_preview_next", number=f"INV-{year}-00001")
    assert page._preview_return.text() == _t("settings.documents.fmt_preview_next", number=f"CN-{year}-00001")
    assert not page._preview_sale.isHidden()


def test_sync_till_preview_explains_the_terminal_prefix(page, monkeypatch):
    from cbpos.core.services.config_service import ConfigService

    monkeypatch.setattr(ConfigService, "get", lambda key, default=None: {"terminal_mode": "terminal"}.get(key, default))
    page.input_terminal_id.setText("TERM-02")
    page.input_fmt_sale.setText("INV-{Y}-{seq:05d}")

    year = datetime.now().strftime("%Y")
    assert f"TERM02-INV-{year}-00001" in page._preview_sale.text()
    assert _t("settings.documents.fmt_terminal_added") in page._preview_sale.text()
    # GRNs are pushed to the Main PC too, so they get the prefix as well (#679).
    assert _t("settings.documents.fmt_terminal_added") in page._preview_purchase.text()


def test_save_all_blocks_an_invalid_format(qapp, db_session, monkeypatch):
    from PyQt6.QtWidgets import QMessageBox

    from cbpos.core.services.config_service import ConfigService
    from cbpos.ui.views.settings_view import SettingsView

    saved = []
    monkeypatch.setattr(ConfigService, "get_all", lambda: {"language": "en", "theme": "Dark", "font_size": 12})
    monkeypatch.setattr(ConfigService, "update_all", saved.append)
    monkeypatch.setattr("cbpos.core.utils.permission_helper.check_permission_with_override", lambda p, w: True)
    warnings = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: warnings.append(a))

    view = SettingsView()
    try:
        doc_page = next(p for p in view.pages if isinstance(p, DocumentPage))
        doc_page.input_fmt_purchase.setText("GRN-{seq:05d}-{Y}")

        view.save_all()

        assert saved == []
        assert len(warnings) == 1
        assert view.stack.currentWidget() is doc_page
    finally:
        view.deleteLater()
