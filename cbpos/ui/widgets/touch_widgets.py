import os

from PyQt6.QtWidgets import (
    QToolButton,
    QVBoxLayout,
    QLabel,
    QSizePolicy,
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QPixmap

# Base directory for product images (user data, not app assets)
from cbpos.config import Config

_IMAGES_DIR = Config.DATA_DIR


class ProductCard(QToolButton):
    """
    A touch-friendly button representing a product.
    Displays product image (if available), name, and price — styled via QSS.
    """

    clicked_product = pyqtSignal(object)  # Emits the product object

    def __init__(self, product, parent=None):
        super().__init__(parent)
        self.product = product
        self.setObjectName("ProductCard")
        self.setMinimumSize(90, 100)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 8)
        layout.setSpacing(4)

        # Product image (shown only if image_path exists and file is valid)
        image_path = getattr(self.product, "image_path", None)
        if image_path:
            full_path = os.path.join(str(_IMAGES_DIR), image_path)
            if os.path.isfile(full_path):
                pixmap = QPixmap(full_path)
                if not pixmap.isNull():
                    self.lbl_image = QLabel()
                    self.lbl_image.setObjectName("ProductCardImage")
                    self.lbl_image.setAlignment(Qt.AlignmentFlag.AlignCenter)
                    self.lbl_image.setFocusPolicy(Qt.FocusPolicy.NoFocus)
                    self.lbl_image.setPixmap(
                        pixmap.scaled(
                            60,
                            60,
                            Qt.AspectRatioMode.KeepAspectRatio,
                            Qt.TransformationMode.SmoothTransformation,
                        )
                    )
                    layout.addWidget(self.lbl_image)

        # Name Label
        self.lbl_name = QLabel(getattr(self.product, "name_en", None) or getattr(self.product, "name", ""))
        self.lbl_name.setObjectName("ProductCardName")
        self.lbl_name.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_name.setWordWrap(True)
        self.lbl_name.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        layout.addWidget(self.lbl_name)

        # Price Label
        self.lbl_price = QLabel(f"{self.product.price:,.2f}")  # noqa: E231
        self.lbl_price.setObjectName("ProductCardPrice")
        self.lbl_price.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_price.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        layout.addWidget(self.lbl_price)

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        self.clicked_product.emit(self.product)


class CategoryButton(QToolButton):
    def __init__(self, category, parent=None):
        super().__init__(parent)
        self.category = category
        self.setObjectName("CategoryTab")
        self.setText(category.name)
        self.setCheckable(True)
        self.setAutoExclusive(True)
        self.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        self.setMinimumHeight(40)
        self.setMinimumWidth(100)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        # Dynamic checked background color (varies per category, can't be pure QSS)
        color = category.color if category.color else "#00BCEB"
        self.setStyleSheet("QToolButton#CategoryTab:checked { background-color: %s; }" % color)
