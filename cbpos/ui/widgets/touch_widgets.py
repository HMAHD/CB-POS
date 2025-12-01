from PyQt6.QtWidgets import (
    QToolButton,
    QVBoxLayout,
    QLabel,
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont


class ProductCard(QToolButton):
    """
    A touch-friendly button representing a product.
    Displays image/icon, name, and price.
    """

    clicked_product = pyqtSignal(object)  # Emits the product object

    def __init__(self, product, parent=None):
        super().__init__(parent)
        self.product = product
        self.setFixedSize(110, 110)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setup_ui()

    def setup_ui(self):
        # Layout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(2)

        # Icon/Image
        icon_label = QLabel()
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # TODO: Load actual image if available
        # if self.product.image_path:
        #     ...
        # else:
        from cbpos.ui.resources.icons import Icons

        icon_label.setPixmap(Icons.get("fa5s.box").pixmap(40, 40))

        # Style
        self.setStyleSheet(
            """
            QToolButton {
                background-color: #003366;
                border: 1px solid #00509E;
                border-radius: 8px;
            }
            QToolButton:hover {
                background-color: #004080;
                border: 1px solid #00BCEB;
            }
            QToolButton:pressed {
                background-color: #002855;
            }
            """
        )

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        self.clicked_product.emit(self.product)


class CategoryButton(QToolButton):
    def __init__(self, category, parent=None):
        super().__init__(parent)
        self.category = category
        self.setText(category.name)
        self.setCheckable(True)
        self.setAutoExclusive(True)
        self.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        self.setMinimumHeight(40)
        self.setMinimumWidth(100)
        self.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))

        # Dynamic color if category has one, else default
        color = category.color if category.color else "#00BCEB"

        self.setStyleSheet(
            """
            QToolButton {{
                background-color: #003366;
                color: white;
                border: 1px solid #00509E;
                border-radius: 4px;
                padding: 5px;
            }}
            QToolButton:checked {{
                background-color: {color};
                color: black;
                border: 1px solid white;
            }}
            """.format(
                color=color
            )
        )
