"""
UI-052 (#546): with Enter reaching the product search again, the Add /
Create buttons' auto-default behaviour also fired on the same Enter, so
the "not found" warning popped up twice.
"""

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtTest import QTest

from cbpos.ui.dialogs import proforma_dialog
from cbpos.ui.dialogs.proforma_dialog import ProformaDialog

pytestmark = pytest.mark.usefixtures("qapp")


def test_enter_on_unknown_product_warns_only_once(db_session, monkeypatch):
    warnings: list[str] = []
    monkeypatch.setattr(proforma_dialog.QMessageBox, "warning", lambda *a, **k: warnings.append(a[1]))

    dialog = ProformaDialog()
    dialog.show()
    dialog.product_search.setFocus()
    dialog.product_search.setText("no-such-product-xyz")
    QTest.keyClick(dialog.product_search, Qt.Key.Key_Return)
    dialog.close()

    assert len(warnings) == 1
