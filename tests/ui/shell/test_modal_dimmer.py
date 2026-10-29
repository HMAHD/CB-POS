"""Unit tests for ModalDimmer overlay and alternating row colors enforcement (#538)."""

import pytest
from PyQt6.QtCore import QEvent, Qt
from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QMainWindow,
    QTableWidget,
    QTreeWidget,
)

from cbpos.core.services.theme_service import ThemeService
from cbpos.ui.dialogs.advanced_search_dialog import AdvancedSearchDialog
from cbpos.ui.dialogs.customer_editor import CustomerEditor
from cbpos.ui.dialogs.permission_dialog import PermissionDialog
from cbpos.ui.dialogs.proforma_dialog import ProformaDialog
from cbpos.ui.dialogs.stock_history_dialog import StockHistoryDialog
from cbpos.ui.dialogs.valuation_dialog import ValuationDialog
from cbpos.ui.widgets.modal_dimmer import (
    ModalDimmer,
    install_modal_dimmer_filter,
)

pytestmark = pytest.mark.usefixtures("qapp")


class TestModalDimmerWidget:
    """Tests the ModalDimmer overlay widget mechanics."""

    def test_dimmer_initial_state_and_properties(self):
        parent = QMainWindow()
        parent.resize(800, 600)
        dimmer = ModalDimmer(parent)

        assert dimmer.testAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents) is True
        assert dimmer.geometry() == parent.rect()
        assert dimmer.objectName() == "ModalDimmer"

    def test_dimmer_resizes_with_parent_window(self):
        parent = QMainWindow()
        parent.resize(600, 400)
        parent.show()
        dimmer = ModalDimmer(parent)
        dimmer.show()

        parent.resize(1024, 768)
        # Process resize event
        QApplication.sendEvent(parent, QEvent(QEvent.Type.Resize))
        assert dimmer.size() == parent.size()

    def test_dimmer_paints_in_dark_and_light_themes(self):
        parent = QMainWindow()
        parent.resize(300, 200)
        dimmer = ModalDimmer(parent)

        ThemeService.current_theme = "Dark"
        dimmer.render(parent)  # triggers paintEvent

        ThemeService.current_theme = "Light"
        dimmer.render(parent)


class TestModalDimmerManagerLifecycle:
    """Tests application-wide modal detection and backdrop dimming."""

    def test_modal_dialog_shows_and_hides_dimmer_on_parent(self):
        mgr = install_modal_dimmer_filter()
        win = QMainWindow()
        win.resize(800, 600)
        win.show()

        dlg = QDialog(win)
        dlg.setModal(True)
        dlg.resize(300, 200)

        dlg.show()
        dimmer = mgr._dimmers.get(win)
        assert dimmer is not None
        assert dimmer.isVisible() is True
        assert dimmer.geometry() == win.rect()

        dlg.hide()
        assert dimmer.isVisible() is False

    def test_non_modal_dialog_does_not_show_dimmer(self):
        mgr = install_modal_dimmer_filter()
        win = QMainWindow()
        win.resize(600, 400)
        win.show()

        dlg = QDialog(win)
        dlg.setModal(False)
        dlg.show()

        dimmer = mgr._dimmers.get(win)
        assert dimmer is None or not dimmer.isVisible()
        dlg.hide()

    def test_nested_modals_maintain_dimmer_until_all_closed(self):
        mgr = install_modal_dimmer_filter()
        win = QMainWindow()
        win.resize(800, 600)
        win.show()

        dlg1 = QDialog(win)
        dlg1.setModal(True)
        dlg1.show()
        dimmer = mgr._dimmers.get(win)
        assert dimmer.isVisible() is True

        dlg2 = QDialog(win)
        dlg2.setModal(True)
        dlg2.show()
        assert dimmer.isVisible() is True

        dlg2.hide()
        assert dimmer.isVisible() is True  # dlg1 is still open

        dlg1.hide()
        assert dimmer.isVisible() is False

    def test_child_modal_dims_parent_modal(self):
        mgr = install_modal_dimmer_filter()
        win = QMainWindow()
        win.show()

        dlg1 = QDialog(win)
        dlg1.setModal(True)
        dlg1.resize(400, 300)
        dlg1.show()

        # Dlg2 is parented to Dlg1
        dlg2 = QDialog(dlg1)
        dlg2.setModal(True)
        dlg2.resize(200, 150)
        dlg2.show()

        dlg1_dimmer = mgr._dimmers.get(dlg1)
        assert dlg1_dimmer is not None
        assert dlg1_dimmer.isVisible() is True

        dlg2.hide()
        assert dlg1_dimmer.isVisible() is False

        dlg1.hide()


class TestAlternatingRowColorsInDialogs:
    """Verifies that dialog tables and trees have alternating row colors enabled."""

    def test_manager_enables_alternating_colors_on_unconfigured_dialog(self):
        install_modal_dimmer_filter()
        win = QMainWindow()
        win.show()

        dlg = QDialog(win)
        dlg.setModal(True)
        tbl = QTableWidget(dlg)
        tree = QTreeWidget(dlg)

        assert tbl.alternatingRowColors() is False
        assert tree.alternatingRowColors() is False

        dlg.show()
        assert tbl.alternatingRowColors() is True
        assert tree.alternatingRowColors() is True
        dlg.hide()

    def test_dialog_instances_have_alternating_row_colors_explicitly_set(self, db_session):
        from cbpos.core.models import Product

        # ValuationDialog table
        vd = ValuationDialog()
        assert vd.table.alternatingRowColors() is True

        # StockHistoryDialog table
        prod = Product(name_en="Test Product", barcode="999001", cost=10, price=20, stock_qty=5)
        sh = StockHistoryDialog(product=prod)
        assert sh.table.alternatingRowColors() is True

        # CustomerEditor tables
        ce = CustomerEditor()
        assert ce.contact_table.alternatingRowColors() is True
        assert ce.points_history_table.alternatingRowColors() is True
        _history_tab = ce.create_history_tab()
        assert ce.history_table.alternatingRowColors() is True

        # PermissionDialog tree
        pd = PermissionDialog()
        assert pd.tree.alternatingRowColors() is True

        # AdvancedSearchDialog table
        asd = AdvancedSearchDialog()
        assert asd.table.alternatingRowColors() is True

        # ProformaDialog items table
        pfd = ProformaDialog()
        assert pfd.items_table.alternatingRowColors() is True
