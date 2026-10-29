"""
#337: only Cash ever showed a shortcut/behavior tag because only Cash
was ever seeded with one -- the architecture is generic (is_cash/
open_drawer/shortcut are real columns any method can set, and
payment_dialog.py wires a QShortcut for whichever method has one), but
it looked like Cash was special. Seed one more common default (Card)
so the pattern is visible out of the box, and add a one-line hint on
the Add/Edit dialog so admins know this applies to every method.
"""

import pytest

from cbpos.ui.views.payment_methods_view import PaymentMethodDialog

pytestmark = pytest.mark.usefixtures("qapp")


class TestAddEditDialogExplainsShortcutsAreForAnyMethod:
    def test_hint_label_is_not_empty(self):
        dialog = PaymentMethodDialog()
        assert dialog.lbl_hint.text() != ""

    def test_hint_does_not_imply_cash_only(self):
        dialog = PaymentMethodDialog()
        assert "not just Cash" in dialog.lbl_hint.text()


class TestSeedDataGivesCardADefaultShortcut:
    def test_demo_seed_gives_card_a_shortcut(self):
        import ast
        from pathlib import Path

        source = Path("scripts/seed.py").read_text()
        tree = ast.parse(source)
        found = False
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and getattr(node.func, "id", "") == "PaymentMethod":
                kwargs = {kw.arg: kw.value for kw in node.keywords}
                name_node = kwargs.get("name")
                if isinstance(name_node, ast.Constant) and name_node.value == "Card":
                    found = True
                    assert "shortcut" in kwargs
                    shortcut_node = kwargs["shortcut"]
                    assert isinstance(shortcut_node, ast.Constant) and shortcut_node.value
        assert found, "Card PaymentMethod not found in scripts/seed.py"

    def test_fresh_install_gives_card_a_shortcut(self):
        import ast
        from pathlib import Path

        source = Path("cbpos/core/services/database_setup_service.py").read_text()
        tree = ast.parse(source)
        found = False
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and getattr(node.func, "id", "") == "PaymentMethod":
                kwargs = {kw.arg: kw.value for kw in node.keywords}
                name_node = kwargs.get("name")
                if isinstance(name_node, ast.Constant) and name_node.value == "Card":
                    found = True
                    assert "shortcut" in kwargs
                    shortcut_node = kwargs["shortcut"]
                    assert isinstance(shortcut_node, ast.Constant) and shortcut_node.value
        assert found, "Card PaymentMethod not found in database_setup_service.py"
