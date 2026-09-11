"""
#329: _generate_barcode_bars() is, by its own comment, "purely
decorative -- it is NOT scannable but looks like a barcode in the
preview." Toggling "Show Barcode" and looking at the preview tells you
nothing about whether the real printed barcode will scan. Add a small
"preview only" label so nobody mistakes this rendering as a
scannability check.
"""

from cbpos.ui.widgets.receipt_preview_widget import ReceiptPreviewWidget
import pytest

pytestmark = pytest.mark.usefixtures("qapp")


class TestBarcodePreviewIsLabeledAsNonScannable:
    def test_barcode_command_renders_a_preview_only_note(self):
        widget = ReceiptPreviewWidget()
        widget.set_commands([{"type": "barcode", "val": "1234567890"}])
        html = widget._browser.toHtml()
        assert "preview only" in html.lower()
