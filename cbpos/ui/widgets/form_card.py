from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QFrame,
    QLabel,
    QLayout,
    QVBoxLayout,
    QWidget,
)


class FormCard(QFrame):
    """Clean, structured container card for grouping form fields without cluttered QGroupBox borders.

    Provides consistent 14px padding, 10px internal spacing, optional accent title header,
    and automatic WA_StyledBackground support.
    """

    def __init__(self, title: str | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("FormCard")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        self._main_layout = QVBoxLayout(self)
        self._main_layout.setContentsMargins(14, 14, 14, 14)
        self._main_layout.setSpacing(10)

        self.title_label: QLabel | None = None
        if title:
            self.title_label = QLabel(title.upper())
            self.title_label.setObjectName("FormCardTitle")
            self._main_layout.addWidget(self.title_label)

    @property
    def content_layout(self) -> QVBoxLayout:
        """Return the underlying content layout."""
        return self._main_layout

    def addWidget(self, widget: QWidget) -> None:
        """Add a child widget to the card."""
        self._main_layout.addWidget(widget)

    def addLayout(self, layout: QLayout) -> None:
        """Add a child sub-layout to the card."""
        self._main_layout.addLayout(layout)

    add_widget = addWidget
    add_layout = addLayout

    def set_title(self, title: str) -> None:
        """Set or update the card's uppercase accent title."""
        if self.title_label is None:
            self.title_label = QLabel(title.upper())
            self.title_label.setObjectName("FormCardTitle")
            self._main_layout.insertWidget(0, self.title_label)
        else:
            self.title_label.setText(title.upper())
