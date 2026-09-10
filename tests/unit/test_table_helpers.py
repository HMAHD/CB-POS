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
