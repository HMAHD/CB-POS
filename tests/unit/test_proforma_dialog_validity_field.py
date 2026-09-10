"""
#368: the Validity field ("30 days") was a plain QSpinBox, reached only
by the generic QSpinBox/QDoubleSpinBox QSS rule already known to render
broken +/- steppers -- the same widget class product_editor.py's own
code comment already flags as broken under this app's QSS, with
QLineEdit + a validator adopted there as the fix.
"""

import pytest
from PyQt6.QtWidgets import QLineEdit

from cbpos.ui.dialogs.proforma_dialog import ProformaDialog

pytestmark = pytest.mark.usefixtures("qapp")


class TestValidityFieldIsALineEdit:
    def test_validity_is_a_line_edit_not_a_spinbox(self, db_session):
        dialog = ProformaDialog()
        assert isinstance(dialog.validity_spin, QLineEdit)

    def test_validity_rejects_out_of_range_values(self, db_session):
        dialog = ProformaDialog()
        validator = dialog.validity_spin.validator()
        assert validator is not None
        assert validator.bottom() == 1
        assert validator.top() == 365

    def test_defaults_to_thirty_days(self, db_session):
        dialog = ProformaDialog()
        assert dialog.validity_spin.text() == "30"

    def test_entered_value_parses_as_an_integer(self, db_session):
        dialog = ProformaDialog()
        dialog.validity_spin.setText("45")
        assert int(dialog.validity_spin.text()) == 45
