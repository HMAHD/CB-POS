"""Capture UI screenshots across 5 busiest screens for Phase 10A UI Gate.

Resolutions: 1366x768
Themes: dark, light
Languages: en, si, ta
Screens:
1. SalesView
2. InventoryView
3. HistoryView
4. DashboardView
5. ReportViewer
"""

import argparse
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
from cbpos.ui.views.dashboard_view import DashboardView  # noqa: E402
from cbpos.ui.views.history_view import HistoryView  # noqa: E402
from cbpos.ui.views.inventory_view import InventoryView  # noqa: E402
from cbpos.ui.views.reports.report_viewer import ReportViewer  # noqa: E402
from cbpos.ui.views.sales_view import SalesView  # noqa: E402


def capture_all(prefix: str = "before"):
    Database()
    app = QApplication.instance() or QApplication(sys.argv)
    ResourceLoader.load_fonts()

    out_dir = project_root / "docs" / "remediation" / "screenshots"
    out_dir.mkdir(parents=True, exist_ok=True)

    themes = ["dark", "light"]
    langs = ["en", "si", "ta"]

    screens = [
        ("sales", SalesView),
        ("inventory", InventoryView),
        ("history", HistoryView),
        ("dashboard", DashboardView),
        ("reports", ReportViewer),
    ]

    for theme in themes:
        ThemeService.apply_theme(theme.capitalize())
        stylesheet = ThemeService.render_stylesheet(theme)
        app.setStyleSheet(stylesheet)

        for lang in langs:
            set_language(lang)

            for name, view_cls in screens:
                try:
                    view = view_cls()
                    view.resize(1366, 768)
                    view.show()
                    app.processEvents()

                    pix = view.grab()
                    filename = f"p10a_{prefix}_{name}_{theme}_{lang}.png"
                    target_path = out_dir / filename
                    pix.save(str(target_path))
                    view.close()
                    view.deleteLater()
                    app.processEvents()
                    print(f"[{prefix.upper()}] Saved {filename}")
                except Exception as e:
                    print(f"Error capturing {name} ({theme}/{lang}): {e}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--prefix", default="before", choices=["before", "after"])
    args = parser.parse_args()
    capture_all(args.prefix)
