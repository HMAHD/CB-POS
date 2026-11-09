"""What the Data Safety Export tab can write out, as data (#697).

One ``ExportType`` per kind of data and one ``ExportFormat`` per file
format. Adding an export means adding an entry here, nothing else.
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date

import pandas as pd

from cbpos.core.services.data_export_service import DataExportService
from cbpos.core.utils.date_ranges import range_for


@dataclass(frozen=True, slots=True)
class ExportType:
    """One kind of data the Export tab can write out (#697).

    Each combo item carries ``key``; logic branches on it, never on the
    translated label (#696). ``fetch`` gets the chosen From/To days and
    may ignore them when ``needs_dates`` is False.
    """

    key: str
    label_key: str
    title: str
    stem: str
    fetch: Callable[[date, date], pd.DataFrame]
    needs_dates: bool = False


@dataclass(frozen=True, slots=True)
class ExportFormat:
    """A file format the Export tab offers."""

    key: str
    label_key: str
    ext: str


def _fetch_sales(start: date, end: date) -> pd.DataFrame:
    """Sales from the start of *start* to the end of *end* (exclusive next-day start)."""
    start_dt, end_dt = range_for(start, end)
    return DataExportService.get_sales_dataframe(start_dt, end_dt)


# Display order is the dict order. Fetchers look DataExportService up at
# call time so the class stays the single place to change (or stub) them.
EXPORT_TYPES: dict[str, ExportType] = {
    t.key: t
    for t in (
        ExportType(
            "products",
            "data_safety.export_type_products",
            "Products",
            "products",
            lambda _s, _e: DataExportService.get_products_dataframe(),
        ),
        ExportType(
            "customers",
            "data_safety.export_type_customers",
            "Customers",
            "customers",
            lambda _s, _e: DataExportService.get_customers_dataframe(),
        ),
        ExportType("sales", "data_safety.export_type_sales", "Sales", "sales", _fetch_sales, needs_dates=True),
    )
}
EXPORT_FORMATS: dict[str, ExportFormat] = {
    f.key: f
    for f in (
        ExportFormat("excel", "data_safety.export_format_excel", ".xlsx"),
        ExportFormat("csv", "data_safety.export_format_csv", ".csv"),
    )
}
