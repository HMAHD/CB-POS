"""Capture UI screenshots for Phase 10B.1 (#932) UI Gate.

Resolutions: 1366x768 (SettingsView) and dialog size (AutosaveRecoveryDialog)
Themes: dark, light
Languages: en, si, ta
Screens:
1. AutosaveRecoveryDialog
2. SettingsView (FeaturesPage at index 10 showing Power-Cut Autosave card)
"""

import os
import sys
from datetime import datetime
from decimal import Decimal
from pathlib import Path

# Force offscreen Qt platform
os.environ["QT_QPA_PLATFORM"] = "offscreen"

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from PyQt6.QtWidgets import QApplication  # noqa: E402

from cbpos.core.database import Database  # noqa: E402
from cbpos.core.services.theme_service import ThemeService  # noqa: E402
from cbpos.i18n import set_language  # noqa: E402
from cbpos.infrastructure.resource_loader import ResourceLoader  # noqa: E402
from cbpos.ui.dialogs.autosave_recovery_dialog import AutosaveRecoveryDialog  # noqa: E402
from cbpos.ui.views.settings_view import SettingsView  # noqa: E402


def capture_all():
    Database()
    app = QApplication.instance() or QApplication(sys.argv)
    ResourceLoader.load_fonts()

    out_dir = project_root / "docs" / "remediation" / "screenshots"
    out_dir.mkdir(parents=True, exist_ok=True)

    summary = {
        "id": 1,
        "terminal_id": "MAIN-01",
        "item_count": 5,
        "total_qty": Decimal("7.000"),
        "total": Decimal("2340.00"),
        "timestamp": datetime(2026, 11, 20, 11, 45, 0),
    }

    themes = ["dark", "light"]
    langs = ["en", "si", "ta"]

    for theme in themes:
        ThemeService.apply_theme(theme.capitalize())
        stylesheet = ThemeService.render_stylesheet(theme)
        app.setStyleSheet(stylesheet)

        for lang in langs:
            set_language(lang)

            # 1. AutosaveRecoveryDialog
            try:
                dlg = AutosaveRecoveryDialog(summary)
                dlg.resize(480, 260)
                dlg.show()
                app.processEvents()
                path = out_dir / f"p10b_b1_autosave_recovery_{theme}_{lang}.png"
                pixmap = dlg.grab()
                pixmap.save(str(path))
                print(f"Saved: {path.name}")
                dlg.close()
                dlg.deleteLater()
            except Exception as e:
                print(f"Error capturing AutosaveRecoveryDialog ({theme}, {lang}): {e}")

            # 2. SettingsView at index 10 (Features Page showing Power-Cut Autosave)
            try:
                view = SettingsView()
                view.resize(1366, 768)
                view.switch_page(10)
                view.show()
                app.processEvents()
                path = out_dir / f"p10b_b1_settings_features_{theme}_{lang}.png"
                pixmap = view.grab()
                pixmap.save(str(path))
                print(f"Saved: {path.name}")
                view.close()
                view.deleteLater()
            except Exception as e:
                print(f"Error capturing SettingsView ({theme}, {lang}): {e}")


if __name__ == "__main__":
    capture_all()
