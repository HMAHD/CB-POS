"""
#303/#304: a price list's name and dates could only ever be set once, at
creation -- there was no edit/rename action anywhere in the UI, and no
way to remove a product's price override once set (only ever change it
to a different number). This covers the new "Edit" button (rename +
date-range edit, reusing PriceListDialog in an edit mode) and the new
right-click "Remove Override" action on the item table.
"""

from datetime import datetime
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from cbpos.core.models import Product
from cbpos.ui.views import pricelist_view as pricelist_view_module
from cbpos.ui.views.pricelist_view import PriceListDialog, PriceListView

pytestmark = pytest.mark.usefixtures("qapp")

_counter = 0


def _next_suffix() -> str:
    global _counter
    _counter += 1
    return str(_counter)


def _make_product(db_session, name, price="100.00"):
    p = Product(barcode=f"PL-{_next_suffix()}", name_en=name, price=Decimal(price), cost=Decimal("50.00"))
    db_session.add(p)
    db_session.flush()
    return p


class TestPriceListDialogEditMode:
    def test_prefills_fields_from_an_existing_price_list(self, db_session):
        view = PriceListView()
        price_list = view.price_list_service.create_price_list(
            f"Happy Hour_{_next_suffix()}",
            start_date=datetime(2026, 1, 1),
            end_date=datetime(2026, 12, 31),
        )

        dialog = PriceListDialog(price_list=price_list)

        assert dialog.name_input.text() == price_list.name
        assert dialog.start_date.date().toPyDate() == price_list.start_date.date()
        assert dialog.end_date.date().toPyDate() == price_list.end_date.date()

    def test_new_dialog_has_empty_name(self, db_session):
        dialog = PriceListDialog()
        assert dialog.name_input.text() == ""


class TestEditPriceList:
    def test_no_selection_shows_information_and_does_not_open_dialog(self, db_session):
        view = PriceListView()
        view.current_list = None

        with (
            patch.object(pricelist_view_module, "QMessageBox") as mock_box,
            patch.object(pricelist_view_module, "PriceListDialog") as mock_dialog_cls,
        ):
            view.edit_price_list()

        mock_box.information.assert_called_once()
        mock_dialog_cls.assert_not_called()

    def test_accepting_the_dialog_renames_the_list_and_refreshes_the_header(self, db_session):
        view = PriceListView()
        price_list = view.price_list_service.create_price_list(f"Old Name_{_next_suffix()}")
        view.load_lists()
        view._on_nav_clicked(price_list)

        new_name = f"New Name_{_next_suffix()}"
        fake_dialog = MagicMock()
        fake_dialog.exec.return_value = 1
        fake_dialog.get_data.return_value = (new_name, price_list.start_date, price_list.end_date)

        with patch.object(pricelist_view_module, "PriceListDialog", return_value=fake_dialog):
            view.edit_price_list()

        assert view.lbl_list_name.text() == new_name
        updated = next(pl for pl in view.price_list_service.get_all_lists() if pl.id == price_list.id)
        assert updated.name == new_name

    def test_declining_the_dialog_leaves_the_list_unchanged(self, db_session):
        view = PriceListView()
        price_list = view.price_list_service.create_price_list(f"Untouched_{_next_suffix()}")
        view.load_lists()
        view._on_nav_clicked(price_list)

        fake_dialog = MagicMock()
        fake_dialog.exec.return_value = 0

        with patch.object(pricelist_view_module, "PriceListDialog", return_value=fake_dialog):
            view.edit_price_list()

        fake_dialog.get_data.assert_not_called()
        updated = next(pl for pl in view.price_list_service.get_all_lists() if pl.id == price_list.id)
        assert updated.name == price_list.name

    def test_service_error_shows_critical_message_and_keeps_old_name(self, db_session):
        view = PriceListView()
        price_list = view.price_list_service.create_price_list(f"KeepMe_{_next_suffix()}")
        other = view.price_list_service.create_price_list(f"Taken_{_next_suffix()}")
        view.load_lists()
        view._on_nav_clicked(price_list)

        fake_dialog = MagicMock()
        fake_dialog.exec.return_value = 1
        fake_dialog.get_data.return_value = (other.name, price_list.start_date, price_list.end_date)

        with (
            patch.object(pricelist_view_module, "PriceListDialog", return_value=fake_dialog),
            patch.object(pricelist_view_module, "QMessageBox") as mock_box,
        ):
            view.edit_price_list()

        mock_box.critical.assert_called_once()
        updated = next(pl for pl in view.price_list_service.get_all_lists() if pl.id == price_list.id)
        assert updated.name == price_list.name


class TestRemoveOverrideContextMenu:
    def _load_row_for(self, view, product):
        for r in range(view.table.rowCount()):
            if view.table.item(r, 0).text() == str(product.id):
                return r
        raise AssertionError("product row not found")

    def test_removing_an_existing_override_deletes_it(self, db_session):
        product = _make_product(db_session, "Widget")
        view = PriceListView()
        price_list = view.price_list_service.create_price_list(f"List_{_next_suffix()}")
        view.current_list = price_list
        view.price_list_service.set_item_price(price_list.id, product.id, Decimal("42.00"))
        view.load_items()

        row = self._load_row_for(view, product)

        with patch.object(pricelist_view_module, "QMessageBox") as mock_box:
            mock_box.StandardButton.Yes = 1
            mock_box.StandardButton.No = 0
            mock_box.question.return_value = 1
            view._remove_item_override(row)

        assert view.price_list_service.get_items(price_list.id) == []

    def test_declining_confirmation_keeps_the_override(self, db_session):
        product = _make_product(db_session, "Gadget")
        view = PriceListView()
        price_list = view.price_list_service.create_price_list(f"List_{_next_suffix()}")
        view.current_list = price_list
        view.price_list_service.set_item_price(price_list.id, product.id, Decimal("42.00"))
        view.load_items()

        row = self._load_row_for(view, product)

        with patch.object(pricelist_view_module, "QMessageBox") as mock_box:
            mock_box.StandardButton.Yes = 1
            mock_box.StandardButton.No = 0
            mock_box.question.return_value = 0
            view._remove_item_override(row)

        items = view.price_list_service.get_items(price_list.id)
        assert len(items) == 1

    def test_context_menu_is_a_no_op_for_a_row_with_no_override(self, db_session):
        product = _make_product(db_session, "NoOverride")
        view = PriceListView()
        price_list = view.price_list_service.create_price_list(f"List_{_next_suffix()}")
        view.current_list = price_list
        view.load_items()

        row = self._load_row_for(view, product)
        assert view.table.item(row, 3).text() == "-"

        with patch.object(pricelist_view_module, "QMenu") as mock_menu_cls:
            view._show_item_context_menu(view.table.visualItemRect(view.table.item(row, 0)).center())

        mock_menu_cls.assert_not_called()

    def test_context_menu_offers_remove_override_for_a_row_with_one(self, db_session):
        product = _make_product(db_session, "HasOverride")
        view = PriceListView()
        price_list = view.price_list_service.create_price_list(f"List_{_next_suffix()}")
        view.current_list = price_list
        view.price_list_service.set_item_price(price_list.id, product.id, Decimal("42.00"))
        view.load_items()

        row = self._load_row_for(view, product)
        position = view.table.visualItemRect(view.table.item(row, 0)).center()

        sentinel_action = object()
        fake_menu = MagicMock()
        fake_menu.addAction.return_value = sentinel_action
        fake_menu.exec.return_value = sentinel_action

        with (
            patch.object(pricelist_view_module, "QMenu", return_value=fake_menu),
            patch.object(view, "_remove_item_override") as mock_remove,
        ):
            view._show_item_context_menu(position)

        mock_remove.assert_called_once_with(row)
