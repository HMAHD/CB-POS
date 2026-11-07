import re
from abc import ABC, abstractmethod
from typing import Any

import pandas as pd

from cbpos.i18n import _t

# Column types a report declares in its render hints (#556), so the table
# formats and aligns each column by what it holds rather than by guessing
# from runtime value types (np.int64, Decimal and None defeated the guess).
MONEY = "money"  # 2 decimals, separators, currency symbol in the header
INT = "int"  # counts: separators, no decimals
QTY = "qty"  # stock quantities: separators, 3 decimals
PERCENT = "percent"  # already-formatted "12.50%" text, right-aligned
DATE = "date"
TEXT = "text"
NUMERIC_COLUMN_TYPES = frozenset({MONEY, INT, QTY, PERCENT})

# Stable report category IDs (#541). A report's ``category`` is one of
# these, never a translated name: the registry keys and orders categories
# by ID, and the sidebar translates the label only when it is drawn, so
# the order is the same in every language and follows a language switch.
CATEGORY_FAVORITES = "favorites"
CATEGORY_SALES = "sales"
CATEGORY_INVENTORY = "inventory"
CATEGORY_FINANCIAL = "financial"
CATEGORY_AUDIT = "audit"
# Fixed business order for the Reports sidebar, Sales first.
CATEGORY_ORDER = (CATEGORY_SALES, CATEGORY_INVENTORY, CATEGORY_FINANCIAL, CATEGORY_AUDIT)
_COL_KEY_RE = re.compile(r"[^a-z0-9]+")


def category_label(category_id: str) -> str:
    """Return the category's display name in the current language."""
    return _t(f"reports.category_{category_id}")


def report_columns(types: dict[str, str]) -> dict[str, dict[str, str]]:
    """Build the ``columns`` render hint from ``{column name: type}``.

    Each column also gets a ``label_key`` (``reports.col_<name>``) so its
    header can be translated once that key exists in the i18n files;
    until then the column name is shown.

    Example: ``report_columns({"Total Sales": MONEY})`` ->
    ``{"Total Sales": {"type": "money", "label_key": "reports.col_total_sales"}}``.
    """
    return {
        name: {"type": col_type, "label_key": "reports.col_" + _COL_KEY_RE.sub("_", name.lower()).strip("_")}
        for name, col_type in types.items()
    }


class BaseReport(ABC):
    """
    Abstract Base Class for all reports in the system.
    """

    @property
    @abstractmethod
    def id(self) -> str:
        """Unique identifier for the report."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable name of the report."""

    @property
    @abstractmethod
    def category(self) -> str:
        """Stable category ID, one of the ``CATEGORY_*`` constants (e.g. ``CATEGORY_SALES``).

        Not a display name: use :func:`category_label` to show it.
        """

    @property
    def required_permission(self) -> str:
        """Required permission code to view or run this report.

        Defaults to Permissions.REPORTS_VIEW_SALES.
        """
        from cbpos.core.constants.permissions import Permissions

        return Permissions.REPORTS_VIEW_SALES

    @abstractmethod
    def get_filter_definitions(self) -> list[dict[str, Any]]:
        """Returns a list of filter definitions required for this report.

        Example::

            [
                {'name': 'date_range', 'type': 'date_range', 'label': 'Date Range'},
                {
                    'name': 'category_id',
                    'type': 'combo',
                    'label': 'Category',
                    'options': [...]
                },
            ]
        """

    @abstractmethod
    def generate(self, filters: dict[str, Any]) -> pd.DataFrame:
        """
        Generates the report data based on the provided filters.
        Returns a Pandas DataFrame.
        """

    def get_render_hints(self) -> dict[str, Any]:
        """Optional per-report visual treatment for the shared table view.

        Every report shares one QTableView/PandasModel, so without this a
        cash flow report's "Net Cash Flow" row looks identical to every
        other row, and money columns render as raw "{:.2f}" -- reports
        default to no hints (identical to today's rendering); override to
        opt in. Supported keys (all optional):

            columns (dict[str, dict]): per-column definitions built with
                report_columns(): ``type`` (money/int/qty/percent/date/text)
                decides formatting and alignment, ``label_key`` the header.
            currency_columns (list[str]): legacy shorthand for money columns.
            total_row_column (str) / total_row_values (list[str]): a row
                whose value in total_row_column is in total_row_values is
                rendered bold with a tinted background.
            color_column (str) / color_map (dict[str, str]): a column
                whose values map to a palette meaning ("success", "danger",
                "warning", "info", "neutral" -- theme-aware) or a hex color.
        """
        return {}

    def get_summary(self, df: pd.DataFrame) -> list[dict[str, Any]]:
        """Optional summary KPI cards to display above the report table (#543).

        Computed from the complete DataFrame (all rows, not just the active page).
        Returns a list of dicts:
            [
                {
                    "key": "total_sales",
                    "title": _t("reports.summary_total_sales"),
                    "value": "Rs. 50,000.00",
                    "icon": Icons.SALES,
                    "color": "#00BCEB",
                },
                ...
            ]
        Default returns [] (no summary cards).
        """
        return []
