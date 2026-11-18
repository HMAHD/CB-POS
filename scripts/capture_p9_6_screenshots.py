"""Generate screenshots for Phase 9.6 UI Gate (#829, #830)."""

import os
import sys
from decimal import Decimal
from pathlib import Path

# Force offscreen Qt platform
os.environ["QT_QPA_PLATFORM"] = "offscreen"

project_root = Path(__file__).parent.parent
sys.path.append(str(project_root))

from PyQt6.QtWidgets import QApplication  # noqa: E402

from cbpos.core.services.theme_service import ThemeService  # noqa: E402
from cbpos.i18n import set_language  # noqa: E402
from cbpos.ui.dialogs.plan_covered_item_chooser_dialog import (  # noqa: E402
    PlanCoveredItemChooserDialog,
)
from cbpos.ui.views.dashboard_view import DashboardView  # noqa: E402
from cbpos.ui.views.reports.report_viewer import ReportViewer  # noqa: E402
from cbpos.ui.views.warranty_claims_board_view import (  # noqa: E402
    WarrantyClaimsBoardView,
)


class DummyProduct:
    def __init__(self, name="1 Year Extended Warranty Plan", price=Decimal("4500.00")):
        self.name_en = name
        self.price = price


def capture_screenshots():
    app = QApplication.instance() or QApplication(sys.argv)
    out_dir = Path("docs/remediation/screenshots")
    out_dir.mkdir(parents=True, exist_ok=True)

    plan_prod = DummyProduct()
    prod1 = DummyProduct("Samsung Galaxy A15 128GB", Decimal("58000.00"))
    prod2 = DummyProduct("Samsung Galaxy A25 256GB", Decimal("75000.00"))
    eligible_lines = [
        {
            "line_id": "line-1",
            "product": prod1,
            "unit_price": Decimal("58000.00"),
            "qty": Decimal("1.000"),
        },
        {
            "line_id": "line-2",
            "product": prod2,
            "unit_price": Decimal("75000.00"),
            "qty": Decimal("1.000"),
        },
    ]

    configs = [
        ("dark", "en"),
        ("light", "en"),
        ("dark", "si"),
        ("dark", "ta"),
    ]

    for theme, lang in configs:
        set_language(lang)
        app.setStyleSheet(ThemeService.render_stylesheet(theme))

        # 1. Plan covered item chooser dialog
        dlg = PlanCoveredItemChooserDialog(plan_prod, eligible_lines)
        dlg.resize(600, 360)
        dlg.show()
        app.processEvents()
        pix = dlg.grab()
        path = out_dir / f"plan_covered_item_chooser_{theme}_{lang}.png"
        pix.save(str(path))
        dlg.close()
        print(f"Saved {path}")

        # 2. Dashboard view with warranty tile
        dash = DashboardView()
        dash.resize(1366, 768)
        # Prepopulate warranty panel counts for presentation
        if hasattr(dash, "warranty_panel"):
            dash.warranty_panel.set_counts(open_count=3, pickup_count=1, supplier_count=2)
        dash.show()
        app.processEvents()
        pix = dash.grab()
        path = out_dir / f"dashboard_warranty_tile_{theme}_{lang}.png"
        pix.save(str(path))
        dash.close()
        print(f"Saved {path}")

        # 3. Report viewer with warranty category
        try:
            rv = ReportViewer()
            rv.resize(1366, 768)
            rv.show()
            app.processEvents()
            pix = rv.grab()
            path = out_dir / f"warranty_reports_{theme}_{lang}.png"
            pix.save(str(path))
            rv.close()
            print(f"Saved {path}")
        except Exception as e:
            print(f"Error saving report viewer: {e}")

        # 4. Warranty claims board with open filter
        try:
            board = WarrantyClaimsBoardView()
            board.set_status_filter("OPEN")
            board.resize(1366, 768)
            board.show()
            app.processEvents()
            pix = board.grab()
            path = out_dir / f"warranty_claims_board_open_{theme}_{lang}.png"
            pix.save(str(path))
            board.close()
            print(f"Saved {path}")
        except Exception as e:
            print(f"Error saving claims board: {e}")

    print("All screenshots generated successfully.")


if __name__ == "__main__":
    capture_screenshots()
