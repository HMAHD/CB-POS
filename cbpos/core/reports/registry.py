from typing import List, Dict, Type
from cbpos.core.reports.base_report import BaseReport


class ReportRegistry:
    """
    Singleton registry to manage available reports.
    """

    _instance = None
    _reports: Dict[str, List[BaseReport]] = {}
    _all_reports: Dict[str, BaseReport] = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(ReportRegistry, cls).__new__(cls)
            cls._instance._reports = {}
            cls._instance._all_reports = {}
        return cls._instance

    def register(self, report_cls: Type[BaseReport]):
        """
        Registers a report class.
        """
        report_instance = report_cls()
        category = report_instance.category

        if category not in self._reports:
            self._reports[category] = []

        self._reports[category].append(report_instance)
        self._all_reports[report_instance.id] = report_instance

    def get_all_categories(self) -> List[str]:
        """Returns a list of all report categories."""
        return sorted(list(self._reports.keys()))

    def get_reports_by_category(self, category: str) -> List[BaseReport]:
        """Returns a list of reports for a specific category."""
        return self._reports.get(category, [])

    def get_report_by_id(self, report_id: str) -> BaseReport:
        """Returns a report instance by its ID."""
        return self._all_reports.get(report_id)
