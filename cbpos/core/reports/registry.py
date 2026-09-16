from cbpos.core.reports.base_report import BaseReport


class ReportRegistry:
    """
    Singleton registry to manage available reports.
    """

    _instance = None
    _reports: dict[str, list[BaseReport]] = {}
    _all_reports: dict[str, BaseReport] = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._reports = {}
            cls._instance._all_reports = {}
        return cls._instance

    def register(self, report_cls: type[BaseReport]):
        """
        Registers a report class. Skips if already registered (duplicate guard).
        """
        report_instance = report_cls()

        if report_instance.id in self._all_reports:
            return

        category = report_instance.category

        if category not in self._reports:
            self._reports[category] = []

        self._reports[category].append(report_instance)
        self._all_reports[report_instance.id] = report_instance

    def get_all_categories(self) -> list[str]:
        """Returns a list of all report categories."""
        return sorted(self._reports.keys())

    def get_reports_by_category(self, category: str) -> list[BaseReport]:
        """Returns a list of reports for a specific category."""
        return self._reports.get(category, [])

    def get_report_by_id(self, report_id: str) -> BaseReport:
        """Returns a report instance by its ID."""
        return self._all_reports.get(report_id)
