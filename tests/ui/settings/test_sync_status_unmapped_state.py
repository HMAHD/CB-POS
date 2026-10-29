"""
#421: an unmapped SyncClient state fell back to the raw internal string
(e.g. "reconnecting") instead of a translated label. Confirms the fallback
now goes through _t("common.unknown") instead.
"""

from cbpos.ui.widgets.sync_status_widget import SyncStatusWidget


def test_unmapped_state_falls_back_to_translated_unknown(qapp):
    widget = SyncStatusWidget()
    widget.set_mode("terminal")
    widget.set_state("reconnecting")

    details = widget._build_details_text()

    assert "reconnecting" not in details
    assert "Unknown" in details
