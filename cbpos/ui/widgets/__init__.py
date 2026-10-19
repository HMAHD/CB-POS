"""Reusable UI widgets for CB POS."""

from cbpos.ui.widgets.date_range_picker import (
    ALL_PRESETS,
    PRESET_CUSTOM,
    PRESET_LAST_7_DAYS,
    PRESET_LAST_30_DAYS,
    PRESET_LAST_MONTH,
    PRESET_LAST_WEEK,
    PRESET_THIS_MONTH,
    PRESET_THIS_WEEK,
    PRESET_TODAY,
    PRESET_YESTERDAY,
    DateRangePicker,
    compute_preset_range,
)
from cbpos.ui.widgets.dialog_footer import make_close_footer, make_dialog_footer
from cbpos.ui.widgets.form_card import FormCard
from cbpos.ui.widgets.modal_dimmer import (
    ModalDimmer,
    ModalDimmerManager,
    install_modal_dimmer_filter,
    uninstall_modal_dimmer_filter,
)
from cbpos.ui.widgets.status_pill_delegate import (
    STATUS_MEANING_ROLE,
    StatusPillDelegate,
    set_status_pill,
)
from cbpos.ui.widgets.table_helpers import (
    NUMERIC_ALIGNMENT,
    RelativeTimeTableWidgetItem,
    align_numeric_headers,
    attach_table_empty_state,
    configure_table_columns,
)

__all__ = [
    "ALL_PRESETS",
    "NUMERIC_ALIGNMENT",
    "PRESET_CUSTOM",
    "PRESET_LAST_7_DAYS",
    "PRESET_LAST_30_DAYS",
    "PRESET_LAST_MONTH",
    "PRESET_LAST_WEEK",
    "PRESET_THIS_MONTH",
    "PRESET_THIS_WEEK",
    "PRESET_TODAY",
    "PRESET_YESTERDAY",
    "STATUS_MEANING_ROLE",
    "DateRangePicker",
    "FormCard",
    "ModalDimmer",
    "ModalDimmerManager",
    "RelativeTimeTableWidgetItem",
    "StatusPillDelegate",
    "align_numeric_headers",
    "attach_table_empty_state",
    "compute_preset_range",
    "configure_table_columns",
    "install_modal_dimmer_filter",
    "make_close_footer",
    "make_dialog_footer",
    "set_status_pill",
    "uninstall_modal_dimmer_filter",
]
