from functools import lru_cache

import qtawesome as qta
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QApplication


@lru_cache(maxsize=256)
def _cached_qta_icon(icon_name: str, color_hex: str) -> QIcon:
    """Cached instantiation of QIcon via qtawesome."""
    return qta.icon(icon_name, color=color_hex)


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
    USERS = "fa5s.user-shield"
    HISTORY = "fa5s.history"
    SETTINGS = "fa5s.cog"
    LOGOUT = "fa5s.sign-out-alt"
    PURCHASE = "fa5s.truck"
    PRICE_LIST = "fa5s.tags"
    PROMOTION = "fa5s.bullhorn"
    DOCUMENTS = "fa5s.folder-open"
    CREDIT_BOOK = "fa5s.book"
    STOCK_TAKE = "fa5s.clipboard-check"
    ADMIN_TOOLS = "fa5s.toolbox"
    CUSTOMER = "fa5s.user-circle"
    POINTS = "fa5s.star"
    STAR_FILLED = "fa5s.star"
    STAR_OUTLINE = "fa5.star"
    REORDER = "fa5s.dolly"

    # Actions
    ADD = "fa5s.plus"
    EDIT = "fa5s.edit"
    DELETE = "fa5s.trash"
    SAVE = "fa5s.save"
    CANCEL = "fa5s.times"
    SEARCH = "fa5s.search"
    SEARCH_BARCODE = "fa5s.barcode"
    SEARCH_CODE = "fa5s.hashtag"
    SEARCH_NAME = "fa5s.font"
    PRINT = "fa5s.print"
    PAY = "fa5s.money-bill-wave"
    HOLD = "fa5s.hand-paper"
    RECALL = "fa5s.history"
    VOID = "fa5s.ban"
    DRAWER = "fa5s.cash-register"
    NOTE = "fa5s.sticky-note"
    PERCENT = "fa5s.percent"
    QTY = "fa5s.sort-numeric-up"

    # Status
    SUCCESS = "fa5s.check-circle"
    WARNING = "fa5s.exclamation-triangle"
    ERROR = "fa5s.times-circle"
    INFO = "fa5s.info-circle"

    @staticmethod
    def get(name: str, color: str | None = None) -> QIcon:
        """Helper to get QIcon with specific color, memoized via LRU cache."""
        resolved_color = color if color is not None else "white"
        if QApplication.instance() is not None:
            return _cached_qta_icon(name, resolved_color)
        return qta.icon(name, color=resolved_color)

    @classmethod
    def clear_cache(cls) -> None:
        """Clear cached QIcon instances (e.g. on theme switch)."""
        _cached_qta_icon.cache_clear()
