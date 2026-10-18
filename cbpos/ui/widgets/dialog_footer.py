"""
Dialog Footer Component and Helpers.

Provides standardized, translated, consistently ordered dialog footers
with visually distinct primary actions and correct autoDefault behavior.
"""

from collections.abc import Callable

from PyQt6.QtWidgets import QHBoxLayout, QPushButton, QWidget

from cbpos.i18n import _t


def make_dialog_footer(
    primary_key: str = "common.save",
    on_primary: Callable[[], None] | None = None,
    cancel_key: str = "common.cancel",
    on_cancel: Callable[[], None] | None = None,
    primary_object_name: str = "BtnSave",
    cancel_object_name: str = "BtnCancel",
    left_widget: QWidget | None = None,
) -> tuple[QHBoxLayout, QPushButton, QPushButton]:
    """Create a standardized dialog footer layout with [Primary] [Cancel] order.

    Args:
        primary_key: i18n translation key for primary action (default: 'common.save').
        on_primary: Callback invoked when primary button is clicked.
        cancel_key: i18n translation key for cancel action (default: 'common.cancel').
        on_cancel: Callback invoked when cancel button is clicked.
        primary_object_name: Object name for QSS targeting (default: 'BtnSave').
        cancel_object_name: Object name for QSS targeting (default: 'BtnCancel').
        left_widget: Optional widget pinned to the left of the footer (e.g. totals/hints).

    Returns:
        tuple of (QHBoxLayout, btn_primary, btn_cancel)
    """
    layout = QHBoxLayout()
    if left_widget is not None:
        layout.addWidget(left_widget)

    layout.addStretch()

    btn_primary = QPushButton(_t(primary_key))
    btn_primary.setObjectName(primary_object_name)
    btn_primary.setProperty("class", "primary")
    btn_primary.setDefault(True)
    if on_primary is not None:
        btn_primary.clicked.connect(on_primary)
    layout.addWidget(btn_primary)

    btn_cancel = QPushButton(_t(cancel_key))
    btn_cancel.setObjectName(cancel_object_name)
    btn_cancel.setProperty("class", "secondary")
    btn_cancel.setAutoDefault(False)
    if on_cancel is not None:
        btn_cancel.clicked.connect(on_cancel)
    layout.addWidget(btn_cancel)

    return layout, btn_primary, btn_cancel
