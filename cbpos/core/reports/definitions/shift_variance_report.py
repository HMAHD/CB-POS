from typing import Any

import pandas as pd
from sqlalchemy import func

from cbpos.core.constants.status import ShiftStatus
from cbpos.core.database import get_db_session
from cbpos.core.models import Shift, User
from cbpos.core.reports.base_report import DATE, MONEY, TEXT, BaseReport, report_columns
from cbpos.i18n import _t


class ShiftVarianceReport(BaseReport):
    """Cross-cashier shortage/overage oversight: every closed shift's expected vs.
    actual cash, with the shortage/overage reason recorded at close.
    """

    @property
    def id(self) -> str:
        """Report identifier."""
        return "shift_variance"

    @property
    def name(self) -> str:
        """Display name."""
        return _t("reports.shift_variance")

    @property
    def category(self) -> str:
        """Report category."""
        return _t("reports.category_audit")

    def get_filter_definitions(self) -> list[dict[str, Any]]:
        """Date range plus an optional cashier filter, populated from active users."""
        with get_db_session() as session:
            users = session.query(User).order_by(User.username).all()
            user_options = [{"id": u.id, "label": u.username} for u in users]

        return [
            {"name": "date_range", "label": "Date Range", "type": "date_range"},
            {
                "name": "user_id",
                "label": "Cashier",
                "type": "combo",
                "options": [{"id": None, "label": "All Cashiers"}, *user_options],
            },
        ]

    def get_render_hints(self) -> dict[str, Any]:
        """Color rows by whether the shift was short, over, or balanced."""
        return {
            "columns": report_columns(
                {
                    "Date": DATE,
                    "Cashier": TEXT,
                    "Terminal": TEXT,
                    "Expected": MONEY,
                    "Actual": MONEY,
                    "Variance": MONEY,
                    "Status": TEXT,
                    "Reason": TEXT,
                    "Notes": TEXT,
                }
            ),
            "color_column": "Status",
            "color_map": {"Short": "danger", "Over": "warning", "Balanced": "success"},
        }

    def generate(self, filters: dict[str, Any] = None) -> pd.DataFrame:
        """List closed shifts with their expected/actual cash and variance.

        Sorted by absolute variance magnitude, largest first, so the shifts
        most worth a manager's attention surface at the top.
        """
        if filters is None:
            filters = {}

        with get_db_session() as session:
            date_range = filters.get("date_range", {})
            start_date = date_range.get("start")
            end_date = date_range.get("end")
            user_id = filters.get("user_id")

            query = session.query(Shift).join(User).filter(Shift.status == ShiftStatus.CLOSED)

            if start_date:
                query = query.filter(func.date(Shift.start_time) >= start_date)
            if end_date:
                query = query.filter(func.date(Shift.start_time) <= end_date)
            if user_id:
                query = query.filter(Shift.user_id == user_id)

            shifts = query.all()

            data = []
            for s in shifts:
                expected = s.expected_cash or 0
                actual = s.actual_cash or 0
                variance = actual - expected

                if variance < 0:
                    status = "Short"
                elif variance > 0:
                    status = "Over"
                else:
                    status = "Balanced"

                data.append(
                    {
                        "Date": s.start_time.strftime("%Y-%m-%d") if s.start_time else "",
                        "Cashier": s.user.username,
                        "Terminal": s.terminal_id or "",
                        "Expected": float(expected),
                        "Actual": float(actual),
                        "Variance": float(variance),
                        "Status": status,
                        "Reason": s.reason_category or "",
                        "Notes": s.notes or "",
                    }
                )

            df = pd.DataFrame(data)
            if not df.empty:
                df = df.reindex(df["Variance"].abs().sort_values(ascending=False).index).reset_index(drop=True)

            return df
