"""
Collapsible product grid panel for touch/visual POS mode.
Displays category tabs and product buttons for quick selection.
"""

import logging
from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QScrollArea,
    QLabel,
    QFrame,
    QGridLayout,
)
from PyQt6.QtCore import Qt, pyqtSignal
from cbpos.core.services.product_service import ProductService
from cbpos.ui.widgets.touch_widgets import ProductCard, CategoryButton

logger = logging.getLogger(__name__)


class ProductGridPanel(QWidget):
    """
    Category-tabbed product button grid for touch mode.
    Emits product_selected when a product is clicked.
    """

    product_selected = pyqtSignal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.product_service = ProductService()
        self.current_category_id = None
        self.setObjectName("ProductGridPanel")
        self._categories_loaded = False
        self._init_ui()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Category tab bar (horizontal scroll)
        self.category_scroll = QScrollArea()
        self.category_scroll.setWidgetResizable(True)
        self.category_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.category_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.category_scroll.setFixedHeight(50)
        self.category_scroll.setFrameShape(QFrame.Shape.NoFrame)

        self.category_container = QWidget()
        self.category_layout = QHBoxLayout(self.category_container)
        self.category_layout.setContentsMargins(5, 5, 5, 5)
        self.category_layout.setSpacing(5)
        self.category_layout.addStretch()

        self.category_scroll.setWidget(self.category_container)
        layout.addWidget(self.category_scroll)

        # Product grid (scrollable)
        self.product_scroll = QScrollArea()
        self.product_scroll.setWidgetResizable(True)
        self.product_scroll.setFrameShape(QFrame.Shape.NoFrame)

        self.grid_container = QWidget()
        self.grid_layout = QGridLayout(self.grid_container)
        self.grid_layout.setContentsMargins(5, 5, 5, 5)
        self.grid_layout.setSpacing(8)

        self.product_scroll.setWidget(self.grid_container)
        layout.addWidget(self.product_scroll)

    def _load_categories(self) -> None:
        """Load category tabs."""
        categories = self.product_service.get_all_categories()

        # "All" button
        btn_all = CategoryButton(type("Cat", (), {"name": "All", "color": "#00BCEB", "id": None})())
        btn_all.setChecked(True)
        btn_all.clicked.connect(lambda: self._on_category_clicked(None))
        self.category_layout.insertWidget(0, btn_all)

        for i, cat in enumerate(categories):
            btn = CategoryButton(cat)
            btn.clicked.connect(lambda checked, c=cat: self._on_category_clicked(c.id))
            self.category_layout.insertWidget(i + 1, btn)

        self._load_products(None)

    def _on_category_clicked(self, category_id) -> None:
        """Handle category tab click."""
        self.current_category_id = category_id
        self._load_products(category_id)

    def _load_products(self, category_id) -> None:
        """Load products into the grid for the selected category."""
        # Clear existing grid
        while self.grid_layout.count():
            child = self.grid_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        if category_id is not None:
            products = self.product_service.get_by_category(category_id)
        else:
            products = self.product_service.get_all_products()[:50]

        if not products:
            lbl = QLabel("No products in this category")
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setStyleSheet("color: #aaa; font-size: 14px; background: transparent;")
            self.grid_layout.addWidget(lbl, 0, 0)
            return

        # Calculate columns based on available width
        cols = max(3, self.width() // 120) if self.width() > 0 else 4

        for i, product in enumerate(products):
            card = ProductCard(product)
            card.clicked_product.connect(self.product_selected.emit)
            row = i // cols
            col = i % cols
            self.grid_layout.addWidget(card, row, col)

    def showEvent(self, event):
        """Load categories on first show."""
        super().showEvent(event)
        if not self._categories_loaded:
            self._categories_loaded = True
            self._load_categories()
