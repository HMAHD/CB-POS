"""
#330: the preview embedded the logo as <img src='file:///...'> pointing
straight at the original full-color file -- so the preview really did
show the selected image, just never what it will look like once
converted to 1-bit thermal dots, which is the part that commonly looks
bad on real hardware. Route the preview through the same
dither_for_thermal_print() the printer now uses, embedded as a data URI
so the preview shows the real thermal output.
"""

import pytest
from PIL import Image

from cbpos.ui.widgets.receipt_preview_widget import ReceiptPreviewWidget

pytestmark = pytest.mark.usefixtures("qapp")


@pytest.fixture
def logo_path(tmp_path):
    path = tmp_path / "logo.png"
    Image.new("RGB", (400, 100), color=(10, 200, 30)).save(path)
    return str(path)


class TestPreviewShowsTheDitheredLogoNotTheRawFile:
    def test_image_command_embeds_a_data_uri_not_a_raw_file_path(self, logo_path):
        widget = ReceiptPreviewWidget()
        widget.set_commands([{"type": "image", "path": logo_path}])
        html = widget._browser.toHtml()
        assert "data:image/png;base64," in html
        assert "file:///" not in html

    def test_missing_or_unreadable_image_does_not_crash_the_preview(self):
        widget = ReceiptPreviewWidget()
        widget.set_commands([{"type": "image", "path": "/no/such/file.png"}])
        # No exception means the defensive fallback held.
        assert widget._browser.toPlainText() is not None
