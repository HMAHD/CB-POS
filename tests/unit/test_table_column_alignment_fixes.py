"""
Five tables shared the same defect: setSectionResizeMode(mode) called with
no column index, applying one resize mode to every column regardless of
content -- so a short column (an ID, a date) stretches while a long one
(a name, a details string) gets Qt's default Interactive width and
truncates. Each of these now gets an explicit, deliberate mode per column
via configure_table_columns() (see UX-077 / #261).
"""

import pytest
from PyQt6.QtWidgets import QHeaderView

from cbpos.ui.dialogs.customer_selection_dialog import CustomerSelectionDialog
from cbpos.ui.views.credit_book_view import CreditBookView
from cbpos.ui.views.inventory_view import InventoryView
from cbpos.ui.views.promotion_view import PromotionView
from cbpos.ui.views.user_view import UserView

pytestmark = pytest.mark.usefixtures("qapp")


class TestCustomerSelectionDialogColumns:
    def test_name_column_stretches_id_and_phone_size_to_contents(self, db_session):
        dialog = CustomerSelectionDialog()
        header = dialog.table.horizontalHeader()

        assert header.sectionResizeMode(0) == QHeaderView.ResizeMode.ResizeToContents
        assert header.sectionResizeMode(1) == QHeaderView.ResizeMode.Stretch
        assert header.sectionResizeMode(2) == QHeaderView.ResizeMode.ResizeToContents


class TestInventoryViewColumns:
    def test_name_column_stretches_others_size_to_contents(self, db_session):
        view = InventoryView()
        header = view.table.horizontalHeader()

        assert header.sectionResizeMode(1) == QHeaderView.ResizeMode.Stretch
        for col in (0, 2, 3, 4, 5):
            assert header.sectionResizeMode(col) == QHeaderView.ResizeMode.ResizeToContents


class TestCreditBookViewColumns:
    def test_name_column_stretches_debt_and_limit_size_to_contents(self, db_session):
        view = CreditBookView()
        header = view.customer_table.horizontalHeader()

        assert header.sectionResizeMode(1) == QHeaderView.ResizeMode.Stretch
        for col in (0, 2, 3, 4):
            assert header.sectionResizeMode(col) == QHeaderView.ResizeMode.ResizeToContents


class TestUserViewActivityLogColumns:
    def test_details_column_stretches_others_size_to_contents(self, db_session):
        view = UserView()
        header = view.log_table.horizontalHeader()

        assert header.sectionResizeMode(4) == QHeaderView.ResizeMode.Stretch
        for col in (0, 1, 2, 3):
            assert header.sectionResizeMode(col) == QHeaderView.ResizeMode.ResizeToContents


class TestPromotionViewColumns:
    def test_name_column_stretches_others_size_to_contents(self, db_session):
        view = PromotionView()
        header = view.table.horizontalHeader()

        assert header.sectionResizeMode(0) == QHeaderView.ResizeMode.Stretch
        for col in (1, 2, 3, 4, 5):
            assert header.sectionResizeMode(col) == QHeaderView.ResizeMode.ResizeToContents
