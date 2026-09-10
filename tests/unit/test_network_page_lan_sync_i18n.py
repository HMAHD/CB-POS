"""
The Network settings page (#334) had almost no explanatory text or
tooltips, which is why "Mode" and "LAN Sync" read as duplicate features.
While fixing that, the LAN Sync tab (Tab 4) turned out to be built
entirely from hardcoded English string literals, and retranslate_ui()
never touched any of its widgets -- so the tab stayed permanently
English regardless of the user's selected language. Both gaps are
fixed in the same commit since they require touching the same lines.
"""

import pytest

from cbpos.ui.views import settings_pages
from cbpos.ui.views.settings_pages import NetworkPage

pytestmark = pytest.mark.usefixtures("qapp")


@pytest.fixture
def page(qapp):
    p = NetworkPage()
    yield p
    p.deleteLater()


class TestModeTabExplainer:
    def test_mode_tab_has_a_non_empty_explainer_distinguishing_it_from_lan_sync(self, page):
        text = page.lbl_mode_explainer.text()
        assert text
        assert text != "settings.network.mode_explainer"

    def test_db_mode_combo_has_a_tooltip(self, page):
        assert page.cmb_db_mode.toolTip()


class TestServerTabTooltips:
    @pytest.mark.parametrize(
        "widget_name",
        ["input_host", "input_port", "input_dbname", "input_user", "input_password", "btn_test"],
    )
    def test_field_has_a_non_empty_tooltip(self, page, widget_name):
        widget = getattr(page, widget_name)
        assert widget.toolTip()


class TestMigrationTabTooltip:
    def test_migrate_button_has_a_tooltip(self, page):
        assert page.btn_migrate.toolTip()


class TestLanSyncTabIsWiredThroughTranslation:
    """Regression test for the newly-discovered bug: Tab 4 was built from
    raw string literals and retranslate_ui() never touched it, so it
    could never change language. Patching _t to a distinguishable
    fake and re-running retranslate_ui() proves every Tab 4 widget's
    text/placeholder/tooltip is actually sourced from _t(), not from a
    literal baked in at construction time.
    """

    @pytest.fixture
    def fake_translate(self, monkeypatch):
        def _t(key, **kwargs):
            rendered = f"[[{key}]]"
            if kwargs:
                rendered += f"|{kwargs}"
            return rendered

        monkeypatch.setattr(settings_pages, "_t", _t)
        return _t

    def test_tab_label_comes_from_translation(self, page, fake_translate):
        page.retranslate_ui()
        assert page.tabs.tabText(3) == "[[settings.network.tab_lan_sync]]"

    def test_static_labels_come_from_translation(self, page, fake_translate):
        page.retranslate_ui()
        assert page.lbl_sync_title.text() == "[[settings.network.sync_title]]"
        assert page.lbl_sync_desc.text() == "[[settings.network.sync_desc]]"
        assert page.lbl_terminal_mode.text() == "[[settings.network.terminal_mode]]"
        assert page.lbl_sync_terminal_id.text() == "[[settings.network.sync_terminal_id]]"
        assert page.lbl_sync_port.text() == "[[settings.network.sync_port]]"
        assert page.lbl_main_pc_addr.text() == "[[settings.network.main_pc_address]]"
        assert page.lbl_sync_interval.text() == "[[settings.network.sync_interval]]"
        assert page.lbl_sync_secret.text() == "[[settings.network.sync_secret]]"

    def test_terminal_mode_combo_items_come_from_translation(self, page, fake_translate):
        page.retranslate_ui()
        assert page.cmb_terminal_mode.itemText(0) == "[[settings.network.terminal_mode_standalone]]"
        assert page.cmb_terminal_mode.itemText(1) == "[[settings.network.terminal_mode_main]]"
        assert page.cmb_terminal_mode.itemText(2) == "[[settings.network.terminal_mode_terminal]]"
        assert page.cmb_terminal_mode.itemData(0) == "standalone"
        assert page.cmb_terminal_mode.itemData(1) == "main"
        assert page.cmb_terminal_mode.itemData(2) == "terminal"

    def test_terminal_mode_combo_preserves_selection_across_retranslate(self, page, fake_translate):
        page.retranslate_ui()
        page.cmb_terminal_mode.setCurrentIndex(2)
        page.retranslate_ui()
        assert page.cmb_terminal_mode.currentData() == "terminal"

    def test_placeholders_come_from_translation(self, page, fake_translate):
        page.retranslate_ui()
        assert page.input_terminal_id.placeholderText() == "[[settings.network.sync_terminal_id_placeholder]]"
        assert page.input_main_pc_addr.placeholderText() == "[[settings.network.main_pc_address_placeholder]]"
        assert page.input_sync_secret.placeholderText() == "[[settings.network.sync_secret_placeholder]]"

    def test_sync_interval_suffix_comes_from_translation(self, page, fake_translate):
        page.retranslate_ui()
        assert page.spin_sync_interval.suffix() == "[[settings.network.sync_interval_suffix]]"

    def test_buttons_come_from_translation(self, page, fake_translate):
        page.retranslate_ui()
        assert page.btn_test_sync.text() == "[[settings.network.btn_test_sync]]"
        assert page.btn_forget_main.text() == "[[settings.network.btn_forget_main]]"

    @pytest.mark.parametrize(
        "widget_name,key",
        [
            ("cmb_terminal_mode", "settings.network.tooltip_terminal_mode"),
            ("input_terminal_id", "settings.network.tooltip_terminal_id"),
            ("spin_sync_port", "settings.network.tooltip_sync_port"),
            ("input_main_pc_addr", "settings.network.tooltip_main_pc_address"),
            ("spin_sync_interval", "settings.network.tooltip_sync_interval"),
            ("input_sync_secret", "settings.network.tooltip_sync_secret"),
            ("btn_test_sync", "settings.network.tooltip_test_sync"),
            ("btn_forget_main", "settings.network.tooltip_forget_main"),
        ],
    )
    def test_lan_sync_field_tooltip_comes_from_translation(self, page, fake_translate, widget_name, key):
        page.retranslate_ui()
        widget = getattr(page, widget_name)
        assert widget.toolTip() == f"[[{key}]]"
