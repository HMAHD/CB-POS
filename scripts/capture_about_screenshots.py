#!/usr/bin/env python3
"""Capture visual verification screenshots for Issue #816 (About dialog & legal viewers).

Captures:
- About dialog in dark and light themes at 1366x768
- Bundled GPL license viewer in dark and light themes
- Sinhala and Tamil expanded-text states
- Failed-link fallback state
"""

import os
import sys
from pathlib import Path

# Ensure offscreen Qt platform
os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PyQt6.QtCore import QSize
from PyQt6.QtWidgets import QApplication, QMessageBox, QWidget

from cbpos.core.services.theme_service import ThemeService
from cbpos.i18n import _t, set_language
from cbpos.ui.dialogs.about_dialog import AboutDialog
from cbpos.ui.dialogs.text_viewer_dialog import TextViewerDialog

OUTPUT_DIR = Path("docs/remediation/screenshots")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def capture_widget(widget: QWidget, filename: str, viewport_size: QSize = QSize(1366, 768)) -> Path:
    """Position widget on a canvas sized 1366x768 and grab screenshot."""
    canvas = QWidget()
    canvas.setObjectName("Canvas")
    canvas.setFixedSize(viewport_size)

    widget.setParent(canvas)
    widget.show()
    widget.adjustSize()

    # Center dialog on canvas
    x = (viewport_size.width() - widget.width()) // 2
    y = max(10, (viewport_size.height() - widget.height()) // 2)
    widget.move(x, y)

    QApplication.processEvents()

    # Grab canvas
    pix = canvas.grab()
    out_path = OUTPUT_DIR / filename
    pix.save(str(out_path), "PNG")
    print(f"Captured: {out_path} ({pix.width()}x{pix.height()})")
    return out_path


def main():
    app = QApplication.instance() or QApplication(sys.argv)
    ThemeService.set_stylesheet_handler(lambda css: app.setStyleSheet(css))

    # 1. About Dialog - Dark Theme (English)
    ThemeService.apply_theme("dark")
    set_language("en")
    dlg1 = AboutDialog()
    capture_widget(dlg1, "about_dialog_dark_en.png")

    # 2. About Dialog - Light Theme (English)
    ThemeService.apply_theme("light")
    set_language("en")
    dlg2 = AboutDialog()
    capture_widget(dlg2, "about_dialog_light_en.png")

    # 3. About Dialog - Dark Theme (Sinhala expanded text)
    ThemeService.apply_theme("dark")
    set_language("si")
    dlg3 = AboutDialog()
    capture_widget(dlg3, "about_dialog_dark_si.png")

    # 4. About Dialog - Dark Theme (Tamil expanded text)
    ThemeService.apply_theme("dark")
    set_language("ta")
    dlg4 = AboutDialog()
    capture_widget(dlg4, "about_dialog_dark_ta.png")

    # 5. Bundled GPL License Viewer - Dark Theme
    ThemeService.apply_theme("dark")
    set_language("en")
    license_text = Path("LICENSE").read_text(encoding="utf-8")
    dlg5 = TextViewerDialog(title="GNU GPLv3 Licence", text=license_text)
    capture_widget(dlg5, "text_viewer_gpl_dark.png")

    # 6. Bundled GPL License Viewer - Light Theme
    ThemeService.apply_theme("light")
    set_language("en")
    dlg6 = TextViewerDialog(title="GNU GPLv3 Licence", text=license_text)
    capture_widget(dlg6, "text_viewer_gpl_light.png")

    # 7. Failed URL Fallback Dialog - Dark Theme
    ThemeService.apply_theme("dark")
    set_language("en")
    box = QMessageBox()
    box.setObjectName("OpenUrlFailedDialog")
    box.setIcon(QMessageBox.Icon.Information)
    box.setWindowTitle(_t("about.title"))
    box.setText(_t("about.open_url_failed", url="https://ceybyte.com/en/docs/"))
    box.addButton(_t("common.copy"), QMessageBox.ButtonRole.ActionRole)
    box.addButton(QMessageBox.StandardButton.Close)
    capture_widget(box, "url_fallback_dialog_dark.png")

    # Reset
    set_language("en")
    ThemeService.apply_theme("dark")
    print("All screenshots successfully captured!")


if __name__ == "__main__":
    main()
