"""UI tests for Price Board dialog and SalesView F11 integration (#931)."""

from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from PyQt6.QtCore import QEvent, Qt
from PyQt6.QtGui import QCloseEvent, QKeyEvent
from PyQt6.QtWidgets import QMessageBox

from cbpos.core.constants.features import Features
from cbpos.core.constants.permissions import Permissions
from cbpos.core.models import Product, Role, User
from cbpos.core.services.price_board_service import PriceBoardItem
from cbpos.i18n import _t
from cbpos.ui.dialogs.price_board_dialog import PriceBoardDialog
from cbpos.ui.dialogs.shortcuts_help_dialog import ShortcutsHelpDialog
from cbpos.ui.views.sales_view import SalesView


@pytest.fixture
def test_admin_user(db_session):
    admin_role = db_session.query(Role).filter_by(name="Admin").first()
    if not admin_role:
        admin_role = Role(name="Admin")
        db_session.add(admin_role)
        db_session.flush()

    user = db_session.query(User).filter_by(username="admin_ui_pb").first()
    if not user:
        user = User(username="admin_ui_pb", pin_hash="hash", role_id=admin_role.id, is_active=True)
        db_session.add(user)
        db_session.commit()
    return user


@pytest.fixture
def flagged_products(db_session):
    p1 = Product(
        barcode="VEG101",
        name_en="Cabbage 1kg",
        name_si="ගෝවා 1kg",
        name_ta="கோஸ் 1kg",
        price=Decimal("180.00"),
        is_active=True,
        price_changes_often=True,
        version_id=1,
    )
    p2 = Product(
        barcode="VEG102",
        name_en="Leeks 1kg",
        name_si="ලීක්ස් 1kg",
        name_ta="லீக்ஸ் 1kg",
        price=Decimal("220.00"),
        is_active=True,
        price_changes_often=True,
        version_id=1,
    )
    db_session.add_all([p1, p2])
    db_session.commit()
    return [p1, p2]


@pytest.mark.ui
class TestPriceBoardDialogUI:
    """Test suite for PriceBoardDialog rendering and interactions."""

    def test_empty_state_when_no_flagged_products(self, qtbot, test_admin_user):
        """When no products are flagged, empty state page is shown."""
        dialog = PriceBoardDialog(acting_user_id=test_admin_user.id)
        qtbot.addWidget(dialog)

        # Mock loader returning empty
        dialog._on_data_loaded([])
        assert dialog.stack.currentIndex() == 1  # Empty state page

    def test_table_populated_with_flagged_items(self, qtbot, test_admin_user, flagged_products):
        """Flagged products populate table with names, barcodes, and prices."""
        dialog = PriceBoardDialog(acting_user_id=test_admin_user.id)
        qtbot.addWidget(dialog)

        items = [
            PriceBoardItem(
                id=p.id,
                barcode=p.barcode,
                name_en=p.name_en,
                name_si=p.name_si,
                name_ta=p.name_ta,
                current_price=p.price,
                version_id=p.version_id,
            )
            for p in flagged_products
        ]
        dialog._on_data_loaded(items)

        assert dialog.stack.currentIndex() == 2  # Content page
        assert dialog.table.rowCount() == 2

        # Check Col 0 (Name), Col 1 (Barcode), Col 2 (Current), Col 3 (New)
        assert dialog.table.item(0, 0).text() == "Cabbage 1kg"
        assert dialog.table.item(0, 1).text() == "VEG101"
        assert "180" in dialog.table.item(0, 2).text()
        assert "180" in dialog.table.item(0, 3).text()

    def test_filter_hides_non_matching_rows(self, qtbot, test_admin_user, flagged_products):
        """Search query filters visible rows by product name or barcode."""
        dialog = PriceBoardDialog(acting_user_id=test_admin_user.id)
        qtbot.addWidget(dialog)

        items = [
            PriceBoardItem(p.id, p.barcode, p.name_en, p.name_si, p.name_ta, p.price, p.version_id)
            for p in flagged_products
        ]
        dialog._on_data_loaded(items)

        dialog.search_input.setText("leeks")
        assert dialog.table.isRowHidden(0) is True  # Cabbage hidden
        assert dialog.table.isRowHidden(1) is False  # Leeks visible

        dialog.search_input.setText("VEG101")
        assert dialog.table.isRowHidden(0) is False  # Cabbage visible
        assert dialog.table.isRowHidden(1) is True  # Leeks hidden

        dialog.search_input.clear()
        assert dialog.table.isRowHidden(0) is False
        assert dialog.table.isRowHidden(1) is False

    def test_cell_change_updates_summary_and_styling(self, qtbot, test_admin_user, flagged_products):
        """Changing new price updates changed count and highlight."""
        dialog = PriceBoardDialog(acting_user_id=test_admin_user.id)
        qtbot.addWidget(dialog)

        items = [
            PriceBoardItem(p.id, p.barcode, p.name_en, p.name_si, p.name_ta, p.price, p.version_id)
            for p in flagged_products
        ]
        dialog._on_data_loaded(items)

        # Initially 0 changed
        assert "changed" not in dialog.lbl_summary.text()

        # Update row 0 price to 200.00 (changed)
        cell = dialog.table.item(0, 3)
        cell.setData(Qt.ItemDataRole.UserRole, Decimal("200.00"))
        dialog._on_cell_changed(0, 3)

        assert "1 changed" in dialog.lbl_summary.text()
        assert cell.font().bold() is True
        assert cell.foreground().color().isValid() is True

        # Revert back to 180.00 (unchanged)
        cell.setData(Qt.ItemDataRole.UserRole, Decimal("180.00"))
        dialog._on_cell_changed(0, 3)

        assert "changed" not in dialog.lbl_summary.text()
        assert cell.font().bold() is False
        assert cell.data(Qt.ItemDataRole.ForegroundRole) is None

    def test_hidden_row_unhidden_on_validation_error(self, qtbot, test_admin_user, flagged_products, monkeypatch):
        """Hidden row is unhidden and search cleared when validation fails on it."""
        dialog = PriceBoardDialog(acting_user_id=test_admin_user.id)
        qtbot.addWidget(dialog)

        items = [
            PriceBoardItem(p.id, p.barcode, p.name_en, p.name_si, p.name_ta, p.price, p.version_id)
            for p in flagged_products
        ]
        dialog._on_data_loaded(items)

        # Set row 0 invalid
        dialog.table.item(0, 3).setData(Qt.ItemDataRole.UserRole, Decimal("-10.00"))
        # Filter to show only row 1 ("leeks")
        dialog.search_input.setText("leeks")
        assert dialog.table.isRowHidden(0) is True

        monkeypatch.setattr(QMessageBox, "warning", lambda *args, **kwargs: None)
        _updates, has_error = dialog._collect_updates()
        assert has_error is True
        assert dialog.table.isRowHidden(0) is False
        assert dialog.search_input.text() == ""

    def test_save_error_localizes_stale_and_permission_denied(self, qtbot, test_admin_user, monkeypatch):
        """StaleProductError and PermissionError display localized messages."""
        dialog = PriceBoardDialog(acting_user_id=test_admin_user.id)
        qtbot.addWidget(dialog)

        critical_messages = []
        monkeypatch.setattr(QMessageBox, "critical", lambda parent, title, msg: critical_messages.append(msg))

        # 1. Stale error
        dialog._on_save_error("Product 'Carrot' was modified by another user.")
        assert len(critical_messages) == 1
        assert _t("price_board.stale_error") == critical_messages[0]

        # 2. Permission error
        dialog._on_save_error("Permission denied: pricing.manage required")
        assert len(critical_messages) == 2
        assert _t("price_board.permission_denied") == critical_messages[1]

    def test_tab_enter_advance_moves_to_next_row(self, qtbot, test_admin_user, flagged_products):
        """Tab/Enter key advance moves to the next row's new price editor."""
        dialog = PriceBoardDialog(acting_user_id=test_admin_user.id)
        qtbot.addWidget(dialog)
        dialog.show()

        items = [
            PriceBoardItem(p.id, p.barcode, p.name_en, p.name_si, p.name_ta, p.price, p.version_id)
            for p in flagged_products
        ]
        dialog._on_data_loaded(items)

        dialog.table.setCurrentCell(0, 3)
        # Advance from row 0
        dialog._advance_to_next_row(0)
        assert dialog.table.currentRow() == 1

        # Advance from last row focuses Save button
        dialog._advance_to_next_row(1)
        assert dialog.btn_save.hasFocus() or dialog.focusWidget() == dialog.btn_save

    def test_save_and_print_labels_action(self, qtbot, test_admin_user, flagged_products, monkeypatch):
        """Save & Print Labels invokes batch update and opens LabelPrintDialog."""
        dialog = PriceBoardDialog(acting_user_id=test_admin_user.id)
        qtbot.addWidget(dialog)

        items = [
            PriceBoardItem(p.id, p.barcode, p.name_en, p.name_si, p.name_ta, p.price, p.version_id)
            for p in flagged_products
        ]
        dialog._on_data_loaded(items)

        # Set new price for row 0
        dialog.table.item(0, 3).setData(Qt.ItemDataRole.UserRole, Decimal("210.00"))

        mock_label_dlg = MagicMock()
        monkeypatch.setattr("cbpos.ui.dialogs.label_print_dialog.LabelPrintDialog", mock_label_dlg)

        with patch.object(dialog.service, "batch_update_prices", return_value=[flagged_products[0].id]):
            dialog._print_labels_after_save = True
            dialog._on_save_success([flagged_products[0].id])

            # LabelPrintDialog was called with preselected IDs
            mock_label_dlg.assert_called_once_with(
                parent=dialog.parent(), preselected_product_ids=[flagged_products[0].id]
            )

    def test_unchanged_row_stale_does_not_block_changed_row_save(
        self, qtbot, test_admin_user, flagged_products, db_session
    ):
        """Only actually changed rows are sent to save worker; unchanged stale rows do not reject the save."""
        dialog = PriceBoardDialog(acting_user_id=test_admin_user.id)
        qtbot.addWidget(dialog)

        items = [
            PriceBoardItem(
                id=flagged_products[0].id,
                barcode="VEG101",
                name_en="Cabbage 1kg",
                name_si="ගෝවා 1kg",
                name_ta="கோஸ் 1kg",
                current_price=Decimal("180.00"),
                version_id=1,
            ),
            PriceBoardItem(
                id=flagged_products[1].id,
                barcode="VEG102",
                name_en="Leeks 1kg",
                name_si="ලීක්ස් 1kg",
                name_ta="லீக்ஸ் 1kg",
                current_price=Decimal("220.00"),
                version_id=1,
            ),
        ]
        dialog._on_data_loaded(items)

        # 1. User updates row 0 (Cabbage) from 180.00 -> 210.00
        dialog.table.item(0, 3).setData(Qt.ItemDataRole.UserRole, Decimal("210.00"))
        dialog._on_cell_changed(0, 3)

        # 2. Row 1 (Leeks) is left unchanged at 220.00.
        # Meanwhile, in the DB, Leeks' version_id is bumped to 2 (e.g. stock movement or edit)
        p2 = db_session.get(Product, flagged_products[1].id)
        p2.version_id = 2
        db_session.commit()

        # 3. User saves. If unchanged rows are submitted, Leeks (expected version 1 != DB version 2) would fail.
        dialog._execute_save()

        # 4. Prove Cabbage was successfully updated to 210.00, and Leeks was unchanged
        p1 = db_session.get(Product, flagged_products[0].id)
        assert p1.price == Decimal("210.00")
        assert p1.version_id == 2
        p2 = db_session.get(Product, flagged_products[1].id)
        assert p2.price == Decimal("220.00")

    def test_price_board_uses_ui_language_not_receipt_language(
        self, qtbot, test_admin_user, flagged_products, monkeypatch
    ):
        """Price Board is operator-facing (D40): names follow UI language, not receipt_language."""
        from cbpos.core.services.config_service import ConfigService
        from cbpos.i18n import set_language

        # 1. UI language is English; receipt_language is configured as Sinhala
        set_language("en")
        monkeypatch.setattr(ConfigService, "get", lambda k: "si" if k == "receipt_language" else None)

        item1 = PriceBoardItem(
            id=flagged_products[0].id,
            barcode="VEG101",
            name_en="Cabbage 1kg",
            name_si="ගෝවා 1kg",
            name_ta="கோஸ் 1kg",
            current_price=Decimal("180.00"),
            version_id=1,
        )
        item2 = PriceBoardItem(
            id=flagged_products[1].id,
            barcode="VEG102",
            name_en="Leeks 1kg",
            name_si="ලීක්ස් 1kg",
            name_ta="லீக்ஸ் 1kg",
            current_price=Decimal("220.00"),
            version_id=1,
        )

        dialog = PriceBoardDialog(acting_user_id=test_admin_user.id)
        qtbot.addWidget(dialog)
        dialog._on_data_loaded([item1, item2])

        # English UI must show English names despite receipt_language being Sinhala (D40)
        assert dialog.table.item(0, 0).text() == "Cabbage 1kg"
        assert dialog.table.item(1, 0).text() == "Leeks 1kg"
        assert item1.get_display_name() == "Cabbage 1kg"

        # Search matches English name
        dialog.search_input.setText("Cabbage")
        assert dialog.table.isRowHidden(0) is False
        assert dialog.table.isRowHidden(1) is True

        # Validation error feedback uses the English name
        dialog.search_input.clear()
        dialog.table.item(0, 3).setData(Qt.ItemDataRole.UserRole, Decimal("-5.00"))
        warning_messages = []
        monkeypatch.setattr(QMessageBox, "warning", lambda p, t, msg: warning_messages.append(msg))
        dialog._collect_updates()
        assert len(warning_messages) == 1
        assert "Cabbage 1kg" in warning_messages[0]

        # 2. Even when receipt_language is Tamil, English UI still shows English
        monkeypatch.setattr(ConfigService, "get", lambda k: "ta" if k == "receipt_language" else None)
        assert item1.get_display_name() == "Cabbage 1kg"
        assert item2.get_display_name() == "Leeks 1kg"

        # 3. When UI language itself is switched to Sinhala, it shows Sinhala
        set_language("si")
        try:
            assert item1.get_display_name() == "ගෝවා 1kg"
            assert item2.get_display_name() == "ලීක්ස් 1kg"
        finally:
            set_language("en")

    def test_blank_input_does_not_commit_or_advance_on_enter(self, qtbot, test_admin_user, flagged_products):
        """Blank editor input must not commit to 0.00 and must not advance on Enter."""
        dialog = PriceBoardDialog(acting_user_id=test_admin_user.id)
        qtbot.addWidget(dialog)
        items = [
            PriceBoardItem(p.id, p.barcode, p.name_en, p.name_si, p.name_ta, p.price, p.version_id)
            for p in flagged_products
        ]
        dialog._on_data_loaded(items)

        dialog.table.setCurrentCell(0, 3)
        index = dialog.table.model().index(0, 3)
        editor = dialog.delegate.createEditor(dialog.table, None, index)
        editor.setText("")

        advance_called = []
        dialog.delegate.advance_requested.connect(lambda row: advance_called.append(row))

        event = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Return, Qt.KeyboardModifier.NoModifier)
        consumed = dialog.delegate.eventFilter(editor, event)

        assert consumed is True
        assert len(advance_called) == 0
        assert dialog.table.item(0, 3).data(Qt.ItemDataRole.UserRole) == Decimal("180.00")

    def test_blank_input_does_not_commit_or_advance_on_tab(self, qtbot, test_admin_user, flagged_products):
        """Blank editor input must not commit to 0.00 and must not advance on Tab."""
        dialog = PriceBoardDialog(acting_user_id=test_admin_user.id)
        qtbot.addWidget(dialog)
        items = [
            PriceBoardItem(p.id, p.barcode, p.name_en, p.name_si, p.name_ta, p.price, p.version_id)
            for p in flagged_products
        ]
        dialog._on_data_loaded(items)

        dialog.table.setCurrentCell(0, 3)
        index = dialog.table.model().index(0, 3)
        editor = dialog.delegate.createEditor(dialog.table, None, index)
        editor.setText("")

        advance_called = []
        dialog.delegate.advance_requested.connect(lambda row: advance_called.append(row))

        event = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Tab, Qt.KeyboardModifier.NoModifier)
        consumed = dialog.delegate.eventFilter(editor, event)

        assert consumed is True
        assert len(advance_called) == 0
        assert dialog.table.item(0, 3).data(Qt.ItemDataRole.UserRole) == Decimal("180.00")

    def test_blank_input_on_focus_loss_blocks_saving(self, qtbot, test_admin_user, flagged_products, monkeypatch):
        """When editor loses focus with blank text, saving is blocked with invalid price warning."""
        dialog = PriceBoardDialog(acting_user_id=test_admin_user.id)
        qtbot.addWidget(dialog)
        items = [
            PriceBoardItem(p.id, p.barcode, p.name_en, p.name_si, p.name_ta, p.price, p.version_id)
            for p in flagged_products
        ]
        dialog._on_data_loaded(items)

        index = dialog.table.model().index(0, 3)
        editor = dialog.delegate.createEditor(dialog.table, None, index)
        editor.setText("")
        # Focus loss causes setModelData to be called
        dialog.delegate.setModelData(editor, dialog.table.model(), index)

        # Blank input must not have become Decimal('0.00')
        assert dialog.table.item(0, 3).data(Qt.ItemDataRole.UserRole) is None

        # Now attempt save
        warnings = []
        monkeypatch.setattr(QMessageBox, "warning", lambda p, t, msg: warnings.append(msg))
        updates, has_error = dialog._collect_updates()

        assert has_error is True
        assert updates == []
        assert len(warnings) == 1
        assert "Cabbage 1kg" in warnings[0]

    def test_explicit_zero_price_is_valid_and_saves(self, qtbot, test_admin_user, flagged_products, monkeypatch):
        """Explicitly typed 0 or 0.00 is valid, updates model, and saves successfully."""
        dialog = PriceBoardDialog(acting_user_id=test_admin_user.id)
        qtbot.addWidget(dialog)
        items = [
            PriceBoardItem(p.id, p.barcode, p.name_en, p.name_si, p.name_ta, p.price, p.version_id)
            for p in flagged_products
        ]
        dialog._on_data_loaded(items)

        index = dialog.table.model().index(0, 3)
        editor = dialog.delegate.createEditor(dialog.table, None, index)
        editor.setText("0.00")
        dialog.delegate.setModelData(editor, dialog.table.model(), index)

        assert dialog.table.item(0, 3).data(Qt.ItemDataRole.UserRole) == Decimal("0.00")

        updates, has_error = dialog._collect_updates()
        assert has_error is False
        assert any(up["product_id"] == flagged_products[0].id and up["new_price"] == Decimal("0.00") for up in updates)

    def test_lone_decimal_point_rejected_by_validator(self, qtbot, test_admin_user, flagged_products):
        """Validator requires at least one digit: '.' is rejected while '1.' and '0' are accepted."""
        dialog = PriceBoardDialog(acting_user_id=test_admin_user.id)
        qtbot.addWidget(dialog)
        index = dialog.table.model().index(0, 3)
        editor = dialog.delegate.createEditor(dialog.table, None, index)

        editor.setText(".")
        assert editor.hasAcceptableInput() is False

        editor.setText("1.")
        assert editor.hasAcceptableInput() is True

        editor.setText("0")
        assert editor.hasAcceptableInput() is True

        editor.setText("0.00")
        assert editor.hasAcceptableInput() is True

        editor.setText("250.75")
        assert editor.hasAcceptableInput() is True

    def test_lone_decimal_point_does_not_commit_or_advance_on_enter(self, qtbot, test_admin_user, flagged_products):
        """Enter on '.' must keep focus on the same editor without committing or advancing."""
        dialog = PriceBoardDialog(acting_user_id=test_admin_user.id)
        qtbot.addWidget(dialog)
        items = [
            PriceBoardItem(p.id, p.barcode, p.name_en, p.name_si, p.name_ta, p.price, p.version_id)
            for p in flagged_products
        ]
        dialog._on_data_loaded(items)

        dialog.table.setCurrentCell(0, 3)
        index = dialog.table.model().index(0, 3)
        editor = dialog.delegate.createEditor(dialog.table, None, index)
        editor.setText(".")

        advance_called = []
        dialog.delegate.advance_requested.connect(lambda row: advance_called.append(row))

        event = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Return, Qt.KeyboardModifier.NoModifier)
        consumed = dialog.delegate.eventFilter(editor, event)

        assert consumed is True
        assert len(advance_called) == 0
        assert dialog.table.item(0, 3).data(Qt.ItemDataRole.UserRole) == Decimal("180.00")

    def test_lone_decimal_point_does_not_commit_or_advance_on_tab(self, qtbot, test_admin_user, flagged_products):
        """Tab on '.' must keep focus on the same editor without committing or advancing."""
        dialog = PriceBoardDialog(acting_user_id=test_admin_user.id)
        qtbot.addWidget(dialog)
        items = [
            PriceBoardItem(p.id, p.barcode, p.name_en, p.name_si, p.name_ta, p.price, p.version_id)
            for p in flagged_products
        ]
        dialog._on_data_loaded(items)

        dialog.table.setCurrentCell(0, 3)
        index = dialog.table.model().index(0, 3)
        editor = dialog.delegate.createEditor(dialog.table, None, index)
        editor.setText(".")

        advance_called = []
        dialog.delegate.advance_requested.connect(lambda row: advance_called.append(row))

        event = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Tab, Qt.KeyboardModifier.NoModifier)
        consumed = dialog.delegate.eventFilter(editor, event)

        assert consumed is True
        assert len(advance_called) == 0
        assert dialog.table.item(0, 3).data(Qt.ItemDataRole.UserRole) == Decimal("180.00")

    def test_unparsable_value_does_not_commit_or_advance_on_enter_or_tab(
        self, qtbot, test_admin_user, flagged_products
    ):
        """Any unparsable text keeps focus on the same editor on Enter or Tab."""
        dialog = PriceBoardDialog(acting_user_id=test_admin_user.id)
        qtbot.addWidget(dialog)
        items = [
            PriceBoardItem(p.id, p.barcode, p.name_en, p.name_si, p.name_ta, p.price, p.version_id)
            for p in flagged_products
        ]
        dialog._on_data_loaded(items)

        dialog.table.setCurrentCell(0, 3)
        index = dialog.table.model().index(0, 3)
        editor = dialog.delegate.createEditor(dialog.table, None, index)
        # Manually force unparsable text
        editor.setText("abc")

        advance_called = []
        dialog.delegate.advance_requested.connect(lambda row: advance_called.append(row))

        # Enter
        event_enter = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Return, Qt.KeyboardModifier.NoModifier)
        assert dialog.delegate.eventFilter(editor, event_enter) is True
        assert len(advance_called) == 0

        # Tab
        event_tab = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Tab, Qt.KeyboardModifier.NoModifier)
        assert dialog.delegate.eventFilter(editor, event_tab) is True
        assert len(advance_called) == 0

    def test_lone_decimal_point_on_focus_loss_blocks_saving(
        self, qtbot, test_admin_user, flagged_products, monkeypatch
    ):
        """Focus loss on '.' must not silently restore old price; saving must be blocked."""
        dialog = PriceBoardDialog(acting_user_id=test_admin_user.id)
        qtbot.addWidget(dialog)
        items = [
            PriceBoardItem(p.id, p.barcode, p.name_en, p.name_si, p.name_ta, p.price, p.version_id)
            for p in flagged_products
        ]
        dialog._on_data_loaded(items)

        index = dialog.table.model().index(0, 3)
        editor = dialog.delegate.createEditor(dialog.table, None, index)
        editor.setText(".")

        # Focus loss invokes setModelData
        dialog.delegate.setModelData(editor, dialog.table.model(), index)

        # Must NOT have silently restored previous valid price Decimal('180.00')
        assert dialog.table.item(0, 3).data(Qt.ItemDataRole.UserRole) is None

        # Attempting save must fail with warning
        warnings = []
        monkeypatch.setattr(QMessageBox, "warning", lambda p, t, msg: warnings.append(msg))
        updates, has_error = dialog._collect_updates()

        assert has_error is True
        assert updates == []
        assert len(warnings) == 1
        assert "Cabbage 1kg" in warnings[0]

    def test_valid_inputs_accepted_and_saved(self, qtbot, test_admin_user, flagged_products, monkeypatch):
        """Explicit 0, 0.00, normal decimals, and trailing-decimal forms (1.) commit and save."""
        dialog = PriceBoardDialog(acting_user_id=test_admin_user.id)
        qtbot.addWidget(dialog)
        items = [
            PriceBoardItem(p.id, p.barcode, p.name_en, p.name_si, p.name_ta, p.price, p.version_id)
            for p in flagged_products
        ]
        dialog._on_data_loaded(items)

        # 1. Trailing-decimal '1.'
        index0 = dialog.table.model().index(0, 3)
        editor0 = dialog.delegate.createEditor(dialog.table, None, index0)
        editor0.setText("1.")
        dialog.delegate.setModelData(editor0, dialog.table.model(), index0)
        assert dialog.table.item(0, 3).data(Qt.ItemDataRole.UserRole) == Decimal("1.00")

        # 2. Normal decimal '250.50'
        index1 = dialog.table.model().index(1, 3)
        editor1 = dialog.delegate.createEditor(dialog.table, None, index1)
        editor1.setText("250.50")
        dialog.delegate.setModelData(editor1, dialog.table.model(), index1)
        assert dialog.table.item(1, 3).data(Qt.ItemDataRole.UserRole) == Decimal("250.50")

        updates, has_error = dialog._collect_updates()
        assert has_error is False
        assert len(updates) == 2

    def test_escape_key_and_reject_ignored_while_saving(self, qtbot, test_admin_user, flagged_products):
        """While saving is in progress, Escape and reject() are ignored; restored after saving ends."""
        dialog = PriceBoardDialog(acting_user_id=test_admin_user.id)
        qtbot.addWidget(dialog)
        dialog.show()

        reject_emitted = []
        dialog.rejected.connect(lambda: reject_emitted.append(True))

        # 1. While saving:
        dialog._set_saving(True)
        assert getattr(dialog, "_is_saving", False) is True

        # Escape key press
        esc_event = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier)
        dialog.keyPressEvent(esc_event)
        assert esc_event.isAccepted() is False
        assert dialog.isVisible() is True
        assert len(reject_emitted) == 0

        # Direct reject() call
        dialog.reject()
        assert dialog.isVisible() is True
        assert len(reject_emitted) == 0

        # 2. When saving ends (e.g. error):
        dialog._set_saving(False)
        assert getattr(dialog, "_is_saving", False) is False

        # Direct reject now closes and emits rejected
        dialog.reject()
        assert dialog.isVisible() is False
        assert len(reject_emitted) == 1

    def test_window_close_event_ignored_while_saving(self, qtbot, test_admin_user, flagged_products):
        """While saving is in progress, window-close event is ignored."""
        dialog = PriceBoardDialog(acting_user_id=test_admin_user.id)
        qtbot.addWidget(dialog)
        dialog.show()

        # 1. While saving:
        dialog._set_saving(True)
        close_event = QCloseEvent()
        dialog.closeEvent(close_event)
        assert close_event.isAccepted() is False
        assert dialog.isVisible() is True

        # 2. When saving ends:
        dialog._set_saving(False)
        close_event2 = QCloseEvent()
        dialog.closeEvent(close_event2)
        assert close_event2.isAccepted() is True

    def test_save_and_print_labels_still_runs_after_successful_commit(
        self, qtbot, test_admin_user, flagged_products, monkeypatch
    ):
        """Save & Print Labels accepts dialog and opens LabelPrintDialog after successful commit."""
        dialog = PriceBoardDialog(acting_user_id=test_admin_user.id)
        qtbot.addWidget(dialog)
        items = [
            PriceBoardItem(p.id, p.barcode, p.name_en, p.name_si, p.name_ta, p.price, p.version_id)
            for p in flagged_products
        ]
        dialog._on_data_loaded(items)
        dialog.table.item(0, 3).setData(Qt.ItemDataRole.UserRole, Decimal("210.00"))

        mock_label_dlg = MagicMock()
        monkeypatch.setattr("cbpos.ui.dialogs.label_print_dialog.LabelPrintDialog", mock_label_dlg)

        dialog._print_labels_after_save = True
        dialog._set_saving(True)

        # Simulate worker finishing successfully
        dialog._on_save_success([flagged_products[0].id])

        assert getattr(dialog, "_is_saving", False) is False
        assert dialog.result() == int(PriceBoardDialog.DialogCode.Accepted)
        mock_label_dlg.assert_called_once_with(parent=dialog.parent(), preselected_product_ids=[flagged_products[0].id])


@pytest.mark.ui
class TestSalesViewPriceBoardShortcut:
    """Test suite for SalesView F11 shortcut and F1 help gating."""

    def test_f1_help_includes_f11_only_when_feature_enabled(self, monkeypatch):
        """ShortcutsHelpDialog includes F11 if and only if Features.PRICE_BOARD is enabled."""
        from cbpos.core.services import feature_flags

        # 1. Feature disabled
        monkeypatch.setattr(feature_flags, "feature_visible", lambda f: False)
        shortcuts_off = ShortcutsHelpDialog._get_shortcuts()
        keys_off = [k for k, _ in shortcuts_off]
        assert "F11" not in keys_off

        # 2. Feature enabled
        monkeypatch.setattr(feature_flags, "feature_visible", lambda f: f == Features.PRICE_BOARD)
        shortcuts_on = ShortcutsHelpDialog._get_shortcuts()
        keys_on = [k for k, _ in shortcuts_on]
        assert "F11" in keys_on
        # Verify F11 is placed between F10 and F12
        f10_idx = keys_on.index("F10")
        f11_idx = keys_on.index("F11")
        f12_idx = keys_on.index("F12")
        assert f10_idx < f11_idx < f12_idx

    def test_f1_help_omits_f11_on_read_only_till_even_when_feature_enabled(self, monkeypatch):
        """ShortcutsHelpDialog omits F11 on tills even when Features.PRICE_BOARD is enabled."""
        from cbpos.core.services import feature_flags
        from cbpos.core.utils import terminal_guard

        monkeypatch.setattr(feature_flags, "feature_visible", lambda f: True)
        monkeypatch.setattr(terminal_guard, "catalog_is_read_only", lambda: True)

        shortcuts = ShortcutsHelpDialog._get_shortcuts()
        keys = [k for k, _ in shortcuts]
        assert "F11" not in keys

    def test_sales_view_open_price_board_blocked_when_feature_disabled(self, monkeypatch):
        """SalesView.open_price_board does nothing when feature flag is disabled."""
        from cbpos.core.services import feature_flags

        monkeypatch.setattr(feature_flags, "feature_visible", lambda f: False)
        mock_override = MagicMock()
        monkeypatch.setattr("cbpos.core.utils.permission_helper.check_permission_with_override", mock_override)

        sales_view = MagicMock(spec=SalesView)
        SalesView.open_price_board(sales_view)

        # Did not attempt permission check or open dialog
        mock_override.assert_not_called()

    def test_sales_view_open_price_board_blocked_on_read_only_till(self, monkeypatch):
        """SalesView.open_price_board returns immediately without permission prompt on a till."""
        from cbpos.core.services import feature_flags
        from cbpos.core.utils import terminal_guard

        monkeypatch.setattr(feature_flags, "feature_visible", lambda f: True)
        monkeypatch.setattr(terminal_guard, "catalog_is_read_only", lambda: True)

        mock_override = MagicMock()
        monkeypatch.setattr("cbpos.core.utils.permission_helper.check_permission_with_override", mock_override)

        mock_dialog_cls = MagicMock()
        monkeypatch.setattr("cbpos.ui.dialogs.price_board_dialog.PriceBoardDialog", mock_dialog_cls)

        sales_view = MagicMock(spec=SalesView)
        SalesView.open_price_board(sales_view)

        # Neither permission check nor dialog creation should happen
        mock_override.assert_not_called()
        mock_dialog_cls.assert_not_called()

    def test_price_board_service_fails_closed_on_till(self, monkeypatch):
        """PriceBoardService.batch_update_prices raises CatalogReadOnlyError on a till."""
        from cbpos.core.services.price_board_service import PriceBoardService
        from cbpos.core.utils import terminal_guard
        from cbpos.core.utils.terminal_guard import CatalogReadOnlyError

        monkeypatch.setattr(terminal_guard, "catalog_is_read_only", lambda: True)

        service = PriceBoardService()
        with pytest.raises(CatalogReadOnlyError):
            service.batch_update_prices(
                updates=[{"product_id": 1, "expected_version_id": 1, "new_price": Decimal("100.00")}],
                acting_user_id=1,
            )

    def test_sales_view_open_price_board_checks_permission_and_opens_dialog(self, monkeypatch):
        """SalesView.open_price_board checks Permissions.PRICING_MANAGE and opens PriceBoardDialog."""
        from cbpos.core.services import feature_flags

        monkeypatch.setattr(feature_flags, "feature_visible", lambda f: True)

        fake_user = MagicMock()
        fake_user.id = 42
        mock_override = MagicMock(return_value=fake_user)
        monkeypatch.setattr("cbpos.core.utils.permission_helper.check_permission_with_override", mock_override)

        mock_dialog_cls = MagicMock()
        mock_dialog_inst = MagicMock()
        mock_dialog_cls.return_value = mock_dialog_inst
        monkeypatch.setattr("cbpos.ui.dialogs.price_board_dialog.PriceBoardDialog", mock_dialog_cls)

        sales_view = MagicMock(spec=SalesView)
        sales_view.side_menu = MagicMock()
        sales_view.side_menu.isVisible.return_value = False

        SalesView.open_price_board(sales_view)

        mock_override.assert_called_once_with(Permissions.PRICING_MANAGE, sales_view)
        mock_dialog_cls.assert_called_once_with(acting_user_id=42, parent=sales_view)
        mock_dialog_inst.exec.assert_called_once()
