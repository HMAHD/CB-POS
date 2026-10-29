import pytest
from PyQt6.QtWidgets import QHeaderView, QTableWidget

from cbpos.ui.widgets.table_helpers import configure_table_columns

pytestmark = pytest.mark.usefixtures("qapp")


class TestConfigureTableColumns:
    def test_applies_the_given_mode_to_each_listed_column(self):
        table = QTableWidget(0, 3)
        header = table.horizontalHeader()

        configure_table_columns(
            header,
            {
                0: QHeaderView.ResizeMode.ResizeToContents,
                1: QHeaderView.ResizeMode.Stretch,
                2: QHeaderView.ResizeMode.ResizeToContents,
            },
        )

        assert header.sectionResizeMode(0) == QHeaderView.ResizeMode.ResizeToContents
        assert header.sectionResizeMode(1) == QHeaderView.ResizeMode.Stretch
        assert header.sectionResizeMode(2) == QHeaderView.ResizeMode.ResizeToContents

    def test_disables_stretch_last_section_by_default(self):
        table = QTableWidget(0, 2)
        header = table.horizontalHeader()
        header.setStretchLastSection(True)

        configure_table_columns(header, {0: QHeaderView.ResizeMode.ResizeToContents})

        assert header.stretchLastSection() is False

    def test_stretch_last_section_can_be_kept_on_explicitly(self):
        table = QTableWidget(0, 2)
        header = table.horizontalHeader()

        configure_table_columns(header, {0: QHeaderView.ResizeMode.ResizeToContents}, stretch_last_section=True)

        assert header.stretchLastSection() is True

    def test_minimum_section_size_floors_column_width(self):
        table = QTableWidget(0, 2)
        header = table.horizontalHeader()

        configure_table_columns(
            header,
            {0: QHeaderView.ResizeMode.ResizeToContents},
            minimum_section_size=80,
        )

        assert header.minimumSectionSize() == 80


class TestBatchTableUpdate:
    def test_batch_table_update_normal_flow_with_sorting_enabled(self):
        from cbpos.ui.widgets.table_helpers import batch_table_update

        table = QTableWidget(5, 3)
        table.setUpdatesEnabled(True)
        table.setSortingEnabled(True)

        with batch_table_update(table) as tbl:
            assert tbl is table
            assert table.updatesEnabled() is False
            assert table.isSortingEnabled() is False

        assert table.updatesEnabled() is True
        assert table.isSortingEnabled() is True

    def test_batch_table_update_preserves_sorting_disabled_state(self):
        from cbpos.ui.widgets.table_helpers import batch_table_update

        table = QTableWidget(5, 3)
        table.setUpdatesEnabled(True)
        table.setSortingEnabled(False)

        with batch_table_update(table):
            assert table.updatesEnabled() is False
            assert table.isSortingEnabled() is False

        assert table.updatesEnabled() is True
        assert table.isSortingEnabled() is False  # Must NOT be forced to True!

    def test_batch_table_update_preserves_state_on_exception(self):
        from cbpos.ui.widgets.table_helpers import batch_table_update

        table = QTableWidget(5, 3)
        table.setUpdatesEnabled(True)
        table.setSortingEnabled(True)

        with pytest.raises(RuntimeError, match="boom"):
            with batch_table_update(table):
                assert table.updatesEnabled() is False
                assert table.isSortingEnabled() is False
                raise RuntimeError("boom")

        assert table.updatesEnabled() is True
        assert table.isSortingEnabled() is True

    def test_batch_table_update_refreshes_empty_state_if_present(self):
        from unittest.mock import MagicMock

        from cbpos.ui.widgets.table_helpers import batch_table_update

        table = QTableWidget(0, 3)
        mock_refresh = MagicMock()
        table.update_empty_state = mock_refresh

        with batch_table_update(table):
            pass

        mock_refresh.assert_called_once()

    def test_batch_table_update_reenables_updates_even_when_parent_has_updates_disabled(self):
        from PyQt6.QtWidgets import QWidget

        from cbpos.ui.widgets.table_helpers import batch_table_update

        parent = QWidget()
        table = QTableWidget(parent)
        parent.setUpdatesEnabled(False)
        assert table.updatesEnabled() is False

        with batch_table_update(table):
            pass

        # When parent updates are restored, table must not be latched False (#891)
        parent.setUpdatesEnabled(True)
        assert table.updatesEnabled() is True


class TestSlottedDTOs:
    def test_core_dtos_do_not_have_dict(self):
        from decimal import Decimal

        from cbpos.core.services.hardware_test_service import HardwareTestResult
        from cbpos.core.services.invoice_service import InvoiceLine, InvoiceTotals
        from cbpos.core.services.price_list_service import BulkAdjustmentRule, BulkPreviewItem
        from cbpos.core.services.refund_breakdown import RefundBreakdown
        from cbpos.core.services.sales_receipt_builder import ItemDisplay
        from cbpos.core.services.stock_count_service import VarianceTotals

        rule = BulkAdjustmentRule("PERCENTAGE_OFF", Decimal("10.0"))
        preview = BulkPreviewItem(
            1, "Item", "Cat", Decimal("10"), Decimal("20"), None, Decimal("18"), Decimal("10"), False, Decimal("0")
        )
        totals = VarianceTotals(Decimal("10"), Decimal("20"))
        line = InvoiceLine("Item", "1", Decimal("10"), Decimal("0"), Decimal("10"))
        inv_tot = InvoiceTotals(Decimal("10"), Decimal("0"), Decimal("10"), Decimal("0"))
        breakdown = RefundBreakdown(Decimal("10"), Decimal("10"), Decimal("0"))
        hw = HardwareTestResult(True, "OK")
        item_disp = ItemDisplay(None, 1, 10, 10, "Item")

        for dto in (rule, preview, totals, line, inv_tot, breakdown, hw, item_disp):
            assert not hasattr(dto, "__dict__"), f"{dto.__class__.__name__} should not have __dict__"
