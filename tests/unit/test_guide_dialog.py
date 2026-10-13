"""Unit tests for reusable GuideDialog component and Email Setup Guide integration."""

from unittest.mock import MagicMock, patch

import pytest
from PyQt6.QtCore import QRect, Qt
from PyQt6.QtWidgets import QApplication, QLabel, QPushButton, QScrollArea

from cbpos.i18n import _t, set_language
from cbpos.ui.dialogs.guide_dialog import GuideDialog
from cbpos.ui.views.settings_pages import ShopInfoPage

pytestmark = pytest.mark.usefixtures("qapp")


@pytest.fixture(autouse=True)
def app_instance():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


class TestGuideDialogBasics:
    def test_guide_dialog_initialization(self):
        steps = [
            ("Step 1 Title", "Step 1 Detail"),
            ("Step 2 Title", "Step 2 Detail"),
        ]
        dlg = GuideDialog(
            title_key="settings.shop_info.email_guide_title",
            steps=steps,
            note_key="settings.shop_info.guide_important_note",
            close_key="common.got_it",
        )

        assert dlg.windowTitle() == _t("settings.shop_info.email_guide_title")
        assert dlg.lbl_heading.text() == _t("settings.shop_info.email_guide_title")
        assert len(dlg.step_frames) == 2
        assert isinstance(dlg.scroll_area, QScrollArea)
        assert isinstance(dlg.btn_close, QPushButton)
        assert dlg.btn_close.text() == _t("common.got_it")
        assert dlg.btn_close.property("class") == "primary"

    def test_step_badge_alignment_and_numbers(self):
        steps = [
            ("Step 1", "Detail 1"),
            ("3", "Step 3", "Detail 3"),
            {"number": "5", "title": "Step 5", "detail": "Detail 5"},
        ]
        dlg = GuideDialog(title_key="settings.shop_info.email_guide_title", steps=steps)

        assert len(dlg.step_frames) == 3

        # Test badge numbers
        b1 = dlg.step_frames[0].findChild(QLabel, "GuideStepNum")
        b2 = dlg.step_frames[1].findChild(QLabel, "GuideStepNum")
        b3 = dlg.step_frames[2].findChild(QLabel, "GuideStepNum")

        assert b1 is not None and b1.text() == "1"
        assert b2 is not None and b2.text() == "3"
        assert b3 is not None and b3.text() == "5"

        # Test badge top alignment inside card layout
        for frame in dlg.step_frames:
            card_layout = frame.layout()
            badge_item = card_layout.itemAt(0)
            assert bool(badge_item.alignment() & Qt.AlignmentFlag.AlignTop)

    def test_warning_note_card_rendering(self):
        steps = [("Step 1", "Detail 1")]
        dlg_with_note = GuideDialog(
            title_key="settings.shop_info.email_guide_title",
            steps=steps,
            note_key="settings.shop_info.guide_important_note",
        )
        assert dlg_with_note.note_card is not None
        assert dlg_with_note.note_card.objectName() == "GuideNote"
        assert dlg_with_note.note_card.property("class") == "warning-hint"
        assert _t("common.important") in dlg_with_note.note_card.text()

        dlg_without_note = GuideDialog(
            title_key="settings.shop_info.email_guide_title",
            steps=steps,
            note_key=None,
        )
        assert dlg_without_note.note_card is None

    def test_screen_height_capping_at_1366x768(self):
        """GuideDialog height must never exceed 85% of screen height (max ~652px on 768px screen)."""
        mock_screen = MagicMock()
        mock_screen.availableGeometry.return_value = QRect(0, 0, 1366, 768)

        steps = [
            ("Step 1", "Long detail " * 20),
            ("Step 2", "Long detail " * 20),
            ("Step 3", "Long detail " * 20),
            ("Step 4", "Long detail " * 20),
            ("Step 5", "Long detail " * 20),
        ]

        with patch.object(QApplication, "primaryScreen", return_value=mock_screen):
            dlg = GuideDialog(
                title_key="settings.shop_info.email_guide_title",
                steps=steps,
                note_key="settings.shop_info.guide_important_note",
            )
            # 85% of 768 is 652
            expected_max_h = int(768 * 0.85)
            assert dlg.maximumHeight() <= expected_max_h
            assert dlg.maximumHeight() <= 652


class TestGuideDialogLocalization:
    @pytest.mark.parametrize("locale", ["en", "si", "ta"])
    def test_guide_dialog_trilingual_rendering(self, locale):
        set_language(locale)
        try:
            guide_steps = [
                ("settings.shop_info.guide_step1_title", "settings.shop_info.guide_step1_detail"),
                ("settings.shop_info.guide_step2_title", "settings.shop_info.guide_step2_detail"),
                ("settings.shop_info.guide_step3_title", "settings.shop_info.guide_step3_detail"),
                ("settings.shop_info.guide_step4_title", "settings.shop_info.guide_step4_detail"),
            ]
            dlg = GuideDialog(
                title_key="settings.shop_info.email_guide_title",
                heading_key="settings.shop_info.email_guide_heading",
                steps=guide_steps,
                note_key="settings.shop_info.guide_important_note",
                close_key="settings.shop_info.guide_btn_close",
            )

            assert dlg.windowTitle() != ""
            assert not dlg.windowTitle().startswith("settings.")
            assert dlg.lbl_heading.text() != ""
            assert not dlg.lbl_heading.text().startswith("settings.")
            assert dlg.btn_close.text() != ""
            assert not dlg.btn_close.text().startswith("settings.")
            assert dlg.note_card is not None
            assert not dlg.note_card.text().startswith("settings.")

            # All 4 steps translated
            for frame in dlg.step_frames:
                heading = frame.findChild(QLabel, "GuideStepHeading")
                detail = frame.findChild(QLabel, "GuideStepDetail")
                assert heading is not None and not heading.text().startswith("settings.")
                assert detail is not None and not detail.text().startswith("settings.")
        finally:
            set_language("en")


class TestShopInfoPageGuideIntegration:
    def test_show_smtp_guide_uses_guide_dialog(self, monkeypatch):
        page = ShopInfoPage()
        dialog_executed = False

        original_init = GuideDialog.__init__

        def mock_init(self, *args, **kwargs):
            nonlocal dialog_executed
            dialog_executed = True
            original_init(self, *args, **kwargs)

        monkeypatch.setattr(GuideDialog, "__init__", mock_init)
        monkeypatch.setattr(GuideDialog, "exec", lambda self: None)

        page._show_smtp_guide()
        assert dialog_executed is True
