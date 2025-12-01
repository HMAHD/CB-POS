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
            {'name': 'category_id', 'type': 'combo', 'label': 'Category', 'options': [...]},
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
