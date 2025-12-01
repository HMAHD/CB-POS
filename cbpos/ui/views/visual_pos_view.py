from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QScrollArea,
    QGridLayout,
)
from PyQt6.QtCore import Qt, pyqtSignal
from cbpos.core.services.product_service import ProductService
from cbpos.ui.widgets.touch_widgets import ProductCard, CategoryButton


class VisualPosView(QWidget):
    """
    Visual POS Interface for touch-friendly item selection.
    """

    item_clicked = pyqtSignal(object)  # Emits product

    def __init__(self):
        super().__init__()
        self.init_ui()
        self.load_categories()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(5)

        # --- Top: Categories ---
        self.category_container = QWidget()
        self.category_layout = QHBoxLayout(self.category_container)
        self.category_layout.setContentsMargins(5, 5, 5, 5)
        self.category_layout.setSpacing(5)
        self.category_layout.setAlignment(Qt.AlignmentFlag.AlignLeft)

        cat_scroll = QScrollArea()
        cat_scroll.setWidgetResizable(True)
        cat_scroll.setWidget(self.category_container)
        cat_scroll.setFixedHeight(60)
        cat_scroll.setStyleSheet("border: none; background: transparent;")
        cat_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        cat_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        layout.addWidget(cat_scroll)

        # --- Center: Product Grid ---
        self.grid_container = QWidget()
        self.product_grid = QGridLayout(self.grid_container)
        self.product_grid.setContentsMargins(5, 5, 5, 5)
        self.product_grid.setSpacing(10)
        self.product_grid.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)

        grid_scroll = QScrollArea()
        grid_scroll.setWidgetResizable(True)
        grid_scroll.setWidget(self.grid_container)
        grid_scroll.setStyleSheet("border: none; background: transparent;")

        layout.addWidget(grid_scroll)

        # Cache for product widgets to avoid recreation
        self.product_widgets = {}  # category_id -> list of widgets

    def load_categories(self):
        """Load categories into the top bar."""
        categories = ProductService.get_all_categories()

        # Clear existing
        for i in reversed(range(self.category_layout.count())):
            self.category_layout.itemAt(i).widget().setParent(None)

        # Add "All" or default? For now just list categories
        for cat in categories:
            btn = CategoryButton(cat)
            btn.clicked.connect(lambda checked, c=cat: self.load_products(c.id))
            self.category_layout.addWidget(btn)

        # Select first one by default if exists
        if self.category_layout.count() > 0:
            first_btn = self.category_layout.itemAt(0).widget()
            first_btn.setChecked(True)
            self.load_products(first_btn.category.id)

    def load_products(self, category_id):
        """Load products for the selected category."""
        # Clear grid
        self.clear_grid()

        products = ProductService.get_products_by_category(category_id)

        row = 0
        col = 0
        max_cols = 4  # Adjust based on width

        for product in products:
            card = ProductCard(product)
            card.clicked_product.connect(self.on_product_clicked)
            self.product_grid.addWidget(card, row, col)

            col += 1
            if col >= max_cols:
                col = 0
                row += 1

    def clear_grid(self):
        """Remove all items from the grid."""
        for i in reversed(range(self.product_grid.count())):
            widget = self.product_grid.itemAt(i).widget()
            if widget:
                widget.setParent(None)

    def on_product_clicked(self, product):
        self.item_clicked.emit(product)
