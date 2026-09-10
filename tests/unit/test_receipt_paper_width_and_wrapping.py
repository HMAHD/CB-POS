"""
#325: the Receipt settings page's live preview hardcoded "80mm" at
construction and never called ReceiptPreviewWidget.set_paper_width(),
so a shop with a real 58mm printer saw their correctly-wrapped 32-char
text floating inside a visibly wider 80mm-shaped preview canvas.

#326: the preview (Qt HTML/CSS engine) and the real ESC/POS printer
(firmware font metrics) each independently decided where a free-form
header/footer line breaks, since neither ever received pre-wrapped
text -- only the fixed two-column price rows were guaranteed identical
between the two renderers.
"""

from cbpos.core.services.config_service import ConfigService

import pytest

from cbpos.core.services.base_receipt_builder import BaseReceiptBuilder
from cbpos.core.services.sales_receipt_builder import SalesReceiptBuilder
from cbpos.ui.views.settings_pages import ReceiptPage

pytestmark = pytest.mark.usefixtures("qapp")


class _FakeConfigStore:
    def __init__(self, initial: dict):
        self._data = dict(initial)

    def get(self, key):
        # Real ConfigService.get() takes only `key` and falls back to
        # DEFAULTS internally -- no `default` parameter. A more permissive
        # mock here previously hid a real TypeError: production code called
        # ConfigService.get("paper_width", "80mm") and crashed the app on
        # launch, while this test's own get(key, default=None) silently
        # accepted the extra argument and passed anyway.
        return self._data.get(key)

    def get_all(self):
        return dict(self._data)

    def set(self, key, value):
        self._data[key] = value

    def update_all(self, data):
        self._data.update(data)


@pytest.fixture
def config_store(monkeypatch):
    store = _FakeConfigStore(dict(ConfigService.DEFAULTS))
    monkeypatch.setattr(ConfigService, "get", store.get)
    monkeypatch.setattr(ConfigService, "get_all", store.get_all)
    monkeypatch.setattr(ConfigService, "set", store.set)
    monkeypatch.setattr(ConfigService, "update_all", store.update_all)
    return store


@pytest.fixture
def page(qapp, config_store):
    """A ReceiptPage with its debounce QTimer stopped at teardown.

    ReceiptPage wires every field's changed signal (including
    txt_header/txt_footer) to a 300ms singleShot QTimer that calls
    _refresh_preview() -> ConfigService.get(...). A test that edits
    those fields but returns before the timer fires leaves it pending;
    once this test's monkeypatch and db_session have torn down, that
    timer can still fire later -- during whatever unrelated test
    happens to be running at that moment -- and hit a reverted
    ConfigService or a closed session. Confirmed empirically: without
    this explicit stop(), a full suite run intermittently failed a
    different, unrelated test every time.
    """
    p = ReceiptPage()
    yield p
    p._refresh_timer.stop()
    p.deleteLater()


class TestReceiptPagePaperWidthSync:
    def test_refresh_preview_applies_the_real_configured_paper_width(self, page, config_store):
        config_store.set("paper_width", "58mm")

        page._refresh_preview()

        assert page._preview._paper_width == "58mm"

    def test_defaults_to_80mm_when_unset(self, page, config_store):
        page._refresh_preview()

        assert page._preview._paper_width == "80mm"

    def test_loading_settings_also_syncs_the_preview_width(self, page, config_store):
        config_store.set("paper_width", "58mm")

        page.load({"receipt_header": "", "receipt_footer": ""})

        assert page._preview._paper_width == "58mm"


class TestCharCountHint:
    def test_typing_a_header_updates_the_hint_immediately(self, page, config_store):
        page.load({})

        page.txt_header.setPlainText("Welcome to our shop")

        assert "19" in page._lbl_header_char_count.text()
        assert "42" in page._lbl_header_char_count.text()

    def test_58mm_paper_shows_the_32_char_budget(self, page, config_store):
        config_store.set("paper_width", "58mm")
        page.load({})

        page.txt_footer.setPlainText("Thanks!")

        assert "32" in page._lbl_footer_char_count.text()


class TestWrapFreeText:
    def test_short_text_is_a_single_line(self):
        assert BaseReceiptBuilder._wrap_free_text("Thank you!", 32) == ["Thank you!"]

    def test_long_text_wraps_at_the_given_width(self):
        text = "Thank you for shopping with us today, come again soon!"
        lines = BaseReceiptBuilder._wrap_free_text(text, 32)

        assert len(lines) > 1
        assert all(len(line) <= 32 for line in lines)

    def test_preserves_explicit_line_breaks(self):
        text = "Line one\nLine two"
        lines = BaseReceiptBuilder._wrap_free_text(text, 42)

        assert lines == ["Line one", "Line two"]

    def test_empty_text_returns_no_lines(self):
        assert BaseReceiptBuilder._wrap_free_text("", 42) == []


class TestReceiptBuilderEmitsPreWrappedHeaderAndFooter:
    def _dummy_sale(self):
        from decimal import Decimal
        from datetime import datetime
        from cbpos.core.models import Sale, SaleItem, Product

        sale = Sale(
            id=1,
            document_number="INV-TEST-1",
            date=datetime.now(),
            total_amount=Decimal("100.00"),
            tax_vat=Decimal("0"),
            tax_sscl=Decimal("0"),
            net_revenue=Decimal("100.00"),
        )
        product = Product(name_en="Widget")
        sale.items = [
            SaleItem(
                product=product,
                qty=Decimal("1"),
                unit_price=Decimal("100.00"),
                original_price=Decimal("100.00"),
                subtotal=Decimal("100.00"),
            )
        ]
        sale.payments = []
        return sale

    def test_long_header_becomes_multiple_pre_wrapped_text_commands(self, config_store):
        long_header = "This is a very long promotional header message that will not fit on one line"
        config_store.set("receipt_header", long_header)
        config_store.set("receipt_footer", "")

        commands = SalesReceiptBuilder.build_receipt(self._dummy_sale())

        header_lines = [c["val"] for c in commands if c.get("type") == "text" and c["val"] in long_header]
        # Confirm it's split, and no single command carries the whole string.
        assert not any(c.get("val") == long_header for c in commands)
        assert len(header_lines) == 0 or all(len(line) <= 42 for line in header_lines)

        # Reconstruct: every wrapped word should still appear somewhere in the commands.
        all_text = " ".join(c["val"] for c in commands if c.get("type") == "text")
        for word in long_header.split():
            assert word in all_text

    def test_long_footer_becomes_multiple_pre_wrapped_text_commands(self, config_store):
        long_footer = "Thank you so much for shopping with us today we really appreciate your business"
        config_store.set("receipt_header", "")
        config_store.set("receipt_footer", long_footer)

        commands = SalesReceiptBuilder.build_receipt(self._dummy_sale())

        assert not any(c.get("val") == long_footer for c in commands)
        all_text = " ".join(c["val"] for c in commands if c.get("type") == "text")
        for word in long_footer.split():
            assert word in all_text

    def test_58mm_wraps_tighter_than_80mm(self, config_store):
        long_header = "This is a very long promotional header message that will not fit on one line"
        config_store.set("receipt_footer", "")

        config_store.set("receipt_header", long_header)
        config_store.set("paper_width", "80mm")
        commands_80 = SalesReceiptBuilder.build_receipt(self._dummy_sale())
        header_lines_80 = [
            c["val"] for c in commands_80 if c.get("type") == "text" and c.get("align") == "center" and c["val"]
        ]

        config_store.set("paper_width", "58mm")
        commands_58 = SalesReceiptBuilder.build_receipt(self._dummy_sale())
        header_lines_58 = [
            c["val"] for c in commands_58 if c.get("type") == "text" and c.get("align") == "center" and c["val"]
        ]

        assert max(len(line) for line in header_lines_58) <= 32
        assert max(len(line) for line in header_lines_80) <= 42
