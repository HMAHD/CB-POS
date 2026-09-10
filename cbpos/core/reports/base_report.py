from abc import ABC, abstractmethod
from typing import List, Dict, Any
import pandas as pd


class BaseReport(ABC):
    """
    Abstract Base Class for all reports in the system.
    """

    @property
    @abstractmethod
    def id(self) -> str:
        """Unique identifier for the report."""
        pass

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable name of the report."""
        pass

    @property
    @abstractmethod
    def category(self) -> str:
        """Category of the report (e.g., 'Sales', 'Inventory')."""
        pass

    @abstractmethod
    def get_filter_definitions(self) -> List[Dict[str, Any]]:
        """
        Returns a list of filter definitions required for this report.
        Example:
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
        pass

    @abstractmethod
    def generate(self, filters: Dict[str, Any]) -> pd.DataFrame:
        """
        Generates the report data based on the provided filters.
        Returns a Pandas DataFrame.
        """
        pass

    def get_render_hints(self) -> Dict[str, Any]:
        """Optional per-report visual treatment for the shared table view.

        Every report shares one QTableView/PandasModel, so without this a
        cash flow report's "Net Cash Flow" row looks identical to every
        other row, and money columns render as raw "{:.2f}" -- reports
        default to no hints (identical to today's rendering); override to
        opt in. Supported keys (all optional):

            currency_columns (list[str]): columns formatted via the app's
                currency formatter instead of raw "{:.2f}".
            total_row_column (str) / total_row_values (list[str]): a row
                whose value in total_row_column is in total_row_values is
                rendered bold with a tinted background.
            color_column (str) / color_map (dict[str, str]): a column
                whose values map to hex colors (e.g. Inflow/Outflow).
        """
        return {}
