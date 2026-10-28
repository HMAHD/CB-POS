"""
LabelPreviewDialog's dark-theme background was #001F3F (Config.COLOR_NAVY)
-- a real named constant, but a dead one from Python's side, and used
almost everywhere else in the stylesheet only as button text color for
contrast on bright buttons, never as a surface tone. Every other dialog
in dark.qss (its immediate neighbor CsvImportDialog included) uses the
standard dialog surface color #1E1E1E. Light theme was already correct.
"""

from pathlib import Path

from PyQt6.QtWidgets import QDialog

STYLES_DIR = Path(__file__).resolve().parents[2] / "cbpos" / "ui" / "styles"


def _load(theme_file: str) -> str:
    content = (STYLES_DIR / theme_file).read_text(encoding="utf-8")
    return content.replace("{{FONT_FAMILY}}", "Sans Serif").replace("{{FONT_SIZE}}", "12px")


class TestLabelPreviewDialogMatchesTheme:
    def test_dark_theme_uses_the_standard_dialog_surface_color(self, qapp):
        qapp.setStyleSheet(_load("dark.qss"))
        try:
            dialog = QDialog()
            dialog.setObjectName("LabelPreviewDialog")
            dialog.show()
            dialog.ensurePolished()
            assert dialog.palette().window().color().name() == "#1e1e1e"
        finally:
            qapp.setStyleSheet("")

    def test_light_theme_was_already_correct(self, qapp):
        qapp.setStyleSheet(_load("light.qss"))
        try:
            dialog = QDialog()
            dialog.setObjectName("LabelPreviewDialog")
            dialog.show()
            dialog.ensurePolished()
            assert dialog.palette().window().color().name() == "#e9ecef"
        finally:
            qapp.setStyleSheet("")
