"""
#293: nothing on the Document Browser screen explained what it's for
or when a shop owner would use it -- no subtitle, no empty-state
guidance, no tooltip. Add a one-line subtitle under the title,
matching the pattern already used for Network Mode's explainer label.
"""

import pytest

from cbpos.i18n import _t
from cbpos.ui.views.document_view import DocumentBrowserView

pytestmark = pytest.mark.usefixtures("qapp")


class TestDocumentBrowserSubtitle:
    def test_subtitle_label_has_a_non_empty_explanatory_text(self, db_session):
        view = DocumentBrowserView()
        assert view.lbl_subtitle.text() == _t("document_browser.subtitle")
        assert view.lbl_subtitle.text() != ""
