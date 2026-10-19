from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDateEdit,
    QDoubleSpinBox,
    QFrame,
    QLineEdit,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)


def make_scrollable_container(
    parent: QWidget | None = None,
    margins: tuple[int, int, int, int] = (0, 0, 0, 0),
    spacing: int = 10,
) -> tuple[QScrollArea, QWidget, QVBoxLayout]:
    """Create a frameless, responsive QScrollArea wrapper for dialog and tab bodies.

    Returns:
        tuple of (scroll_area, container_widget, container_layout)
    """
    scroll = QScrollArea(parent)
    scroll.setObjectName("DialogScrollArea")
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QFrame.Shape.NoFrame)

    container = QWidget()
    layout = QVBoxLayout(container)
    layout.setContentsMargins(*margins)
    layout.setSpacing(spacing)

    scroll.setWidget(container)
    return scroll, container, layout


def protect_vertical_sizing(root_widget: QWidget) -> None:
    """Protect inputs and checkboxes from vertical crushing on short viewports.

    Sets QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, and QDateEdit to Fixed vertical
    policy, and QCheckBox to Minimum vertical policy so check marks never clip.
    """
    input_types = (QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QDateEdit)
    for widget in root_widget.findChildren(input_types):
        sp = widget.sizePolicy()
        if sp.verticalPolicy() != QSizePolicy.Policy.Fixed:
            sp.setVerticalPolicy(QSizePolicy.Policy.Fixed)
            widget.setSizePolicy(sp)

    for cb in root_widget.findChildren(QCheckBox):
        sp = cb.sizePolicy()
        if sp.verticalPolicy() != QSizePolicy.Policy.Fixed:
            sp.setVerticalPolicy(QSizePolicy.Policy.Fixed)
            cb.setSizePolicy(sp)
