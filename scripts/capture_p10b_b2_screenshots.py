"""Capture UI screenshots for Phase 10B.2 (#931) UI Gate.

Resolutions: 1366x768 (SalesView / PriceBoardDialog modal) and dialog size (920x600)
Themes: dark, light
Languages: en, si, ta
Screens:
1. PriceBoardDialog (content state with items)
2. PriceBoardDialog (empty state)
3. SettingsView (Features page showing Price Board toggle)
"""

import os
import sys
from decimal import Decimal
from pathlib import Path

# Force offscreen Qt platform
os.environ["QT_QPA_PLATFORM"] = "offscreen"

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from PyQt6.QtWidgets import QApplication  # noqa: E402

from cbpos.core.database import Database  # noqa: E402
from cbpos.core.services.price_board_service import PriceBoardItem  # noqa: E402
from cbpos.core.services.theme_service import ThemeService  # noqa: E402
from cbpos.i18n import set_language  # noqa: E402
from cbpos.infrastructure.resource_loader import ResourceLoader  # noqa: E402
from cbpos.ui.dialogs.price_board_dialog import PriceBoardDialog  # noqa: E402
from cbpos.ui.views.settings_view import SettingsView  # noqa: E402


def capture_all():
    Database()
    app = QApplication.instance() or QApplication(sys.argv)
    ResourceLoader.load_fonts()

    out_dir = project_root / "docs" / "remediation" / "screenshots"
    out_dir.mkdir(parents=True, exist_ok=True)

    sample_items = [
        PriceBoardItem(1, "VEG001", "Carrot 1kg", "කැරට් 1kg", "கேரட் 1kg", Decimal("250.00"), 1),
        PriceBoardItem(2, "VEG002", "Beans 1kg", "බෝංචි 1kg", "பீன்ஸ் 1kg", Decimal("320.00"), 1),
        PriceBoardItem(3, "GAS001", "Litro Gas 12.5kg", "ලිට්‍රෝ ගෑස් 12.5kg", "லிட்ரோ கேஸ் 12.5kg", Decimal("3690.00"), 1),
        PriceBoardItem(
            4, "CEM001", "Tokyo Super Cement 50kg", "ටෝකියෝ සිමෙන්ති 50kg", "டோக்கியோ சிமெண்ட் 50kg", Decimal("2250.00"), 1
        ),
        PriceBoardItem(5, "FISH01", "Kelawalla (Tuna) 1kg", "කෙලවල්ලා 1kg", "சூரை மீன் 1kg", Decimal("1600.00"), 1),
    ]

    themes = ["dark", "light"]
    langs = ["en", "si", "ta"]

    for theme in themes:
        ThemeService.apply_theme(theme.capitalize())
        stylesheet = ThemeService.render_stylesheet(theme)
        app.setStyleSheet(stylesheet)

        for lang in langs:
            set_language(lang)

            # 1. PriceBoardDialog content state
            try:
                dlg = PriceBoardDialog(acting_user_id=1, initial_items=sample_items)
                dlg.resize(920, 600)
                dlg.show()
                app.processEvents()
                path = out_dir / f"p10b_b2_price_board_content_{theme}_{lang}.png"
                pixmap = dlg.grab()
                pixmap.save(str(path))
                print(f"Saved: {path.name}")
                dlg.close()
                dlg.deleteLater()
            except Exception as e:
                print(f"Error capturing PriceBoardDialog content ({theme}, {lang}): {e}")

            # 2. PriceBoardDialog empty state
            try:
                dlg_empty = PriceBoardDialog(acting_user_id=1, initial_items=[])
                dlg_empty.resize(920, 600)
                dlg_empty.show()
                app.processEvents()
                path = out_dir / f"p10b_b2_price_board_empty_{theme}_{lang}.png"
                pixmap = dlg_empty.grab()
                pixmap.save(str(path))
                print(f"Saved: {path.name}")
                dlg_empty.close()
                dlg_empty.deleteLater()
            except Exception as e:
                print(f"Error capturing PriceBoardDialog empty ({theme}, {lang}): {e}")

            # 3. SettingsView at index 10 (Features Page showing Price Board)
            try:
                view = SettingsView()
                view.resize(1366, 768)
                view.switch_page(10)
                view.show()
                app.processEvents()
                path = out_dir / f"p10b_b2_settings_features_{theme}_{lang}.png"
                pixmap = view.grab()
                pixmap.save(str(path))
                print(f"Saved: {path.name}")
                view.close()
                view.deleteLater()
            except Exception as e:
                print(f"Error capturing SettingsView ({theme}, {lang}): {e}")


if __name__ == "__main__":
    capture_all()
