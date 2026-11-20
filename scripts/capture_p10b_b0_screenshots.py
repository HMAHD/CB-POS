"""Capture UI screenshots for Phase 10B.0 (#942) UI Gate.

Resolutions: 1366x768 (SettingsView) and dialog size (SetupWizard)
Themes: dark, light
Languages: en, si, ta
Screens:
1. SetupWizard (Step 2: Shop Type preset selection)
2. SettingsView (FeaturesPage at index 10)
"""

import os
import sys
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
from cbpos.ui.dialogs.setup_wizard import SetupWizard  # noqa: E402
from cbpos.ui.views.settings_view import SettingsView  # noqa: E402


def capture_all():
    Database()
    app = QApplication.instance() or QApplication(sys.argv)
    ResourceLoader.load_fonts()

    out_dir = project_root / "docs" / "remediation" / "screenshots"
    out_dir.mkdir(parents=True, exist_ok=True)

    themes = ["dark", "light"]
    langs = ["en", "si", "ta"]

    for theme in themes:
        ThemeService.apply_theme(theme.capitalize())
        stylesheet = ThemeService.render_stylesheet(theme)
        app.setStyleSheet(stylesheet)

        for lang in langs:
            set_language(lang)

            # 1. SetupWizard at step 1 (Shop Type)
            try:
                wiz = SetupWizard(ask_admin_pin=True)
                wiz.input_shop_name.setText("Ceylon Byte Store")
                wiz.go_next()  # Move to Step 1 (Shop Type)
                wiz.resize(640, 520)
                wiz.show()
                app.processEvents()
                path = out_dir / f"p10b_b0_setup_wizard_{theme}_{lang}.png"
                pixmap = wiz.grab()
                pixmap.save(str(path))
                print(f"Saved: {path.name}")
                wiz.close()
                wiz.deleteLater()
            except Exception as e:
                print(f"Error capturing SetupWizard ({theme}, {lang}): {e}")

            # 2. SettingsView at index 10 (Features Page)
            try:
                view = SettingsView()
                view.resize(1366, 768)
                view.switch_page(10)
                view.show()
                app.processEvents()
                path = out_dir / f"p10b_b0_settings_features_{theme}_{lang}.png"
                pixmap = view.grab()
                pixmap.save(str(path))
                print(f"Saved: {path.name}")
                view.close()
                view.deleteLater()
            except Exception as e:
                print(f"Error capturing SettingsView ({theme}, {lang}): {e}")

    print("UI screenshot capture completed.")


if __name__ == "__main__":
    capture_all()
