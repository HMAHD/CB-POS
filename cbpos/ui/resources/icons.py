import qtawesome as qta
from PyQt6.QtGui import QIcon


class Icons:
    """
    Centralized icon management using FontAwesome via qtawesome.
    """

    # Navigation
    DASHBOARD = "fa5s.tachometer-alt"
    SALES = "fa5s.shopping-cart"
    INVENTORY = "fa5s.boxes"
    REPORTS = "fa5s.chart-line"
    CUSTOMERS = "fa5s.users"
    HISTORY = "fa5s.history"
    SETTINGS = "fa5s.cog"
    LOGOUT = "fa5s.sign-out-alt"
    PURCHASE = "fa5s.truck"

    # Actions
    ADD = "fa5s.plus"
    EDIT = "fa5s.edit"
    DELETE = "fa5s.trash"
    SAVE = "fa5s.save"
    CANCEL = "fa5s.times"
    SEARCH = "fa5s.search"
    PRINT = "fa5s.print"
    PAY = "fa5s.money-bill-wave"
    HOLD = "fa5s.hand-paper"
    RECALL = "fa5s.history"
    VOID = "fa5s.ban"

    # Status
    SUCCESS = "fa5s.check-circle"
    WARNING = "fa5s.exclamation-triangle"
    ERROR = "fa5s.times-circle"
    INFO = "fa5s.info-circle"

    @staticmethod
    def get(name: str, color: str = "white") -> QIcon:
        """Helper to get QIcon with specific color."""
        return qta.icon(name, color=color)
