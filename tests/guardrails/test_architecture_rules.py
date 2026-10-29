"""Codebase-wide architecture rules (CLAUDE.md "Modular MVC Pattern").

These replace per-screen tests that read one module's source as text.
"""

import ast
import inspect
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
UI_ROOT = ROOT / "cbpos" / "ui"

# UI modules allowed to import the database, each with its reason.
_DB_IMPORT_ALLOWED = {
    "cbpos/ui/app_restart.py": "disposes the engine so the file can be replaced before a restart",
    "cbpos/ui/views/settings_pages/network.py": "connection test; moves into a service with the #799 Network Setup rewrite",
}


def _ui_modules():
    for path in sorted(UI_ROOT.rglob("*.py")):
        yield path.relative_to(ROOT).as_posix(), ast.parse(path.read_text(encoding="utf-8"))


def test_ui_never_imports_the_database():
    offenders = []
    for rel, tree in _ui_modules():
        if rel in _DB_IMPORT_ALLOWED:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module == "cbpos.core.database":
                offenders.append(f"{rel}:{node.lineno}")
            if isinstance(node, ast.Import) and any(a.name == "cbpos.core.database" for a in node.names):
                offenders.append(f"{rel}:{node.lineno}")
    assert offenders == [], "UI code must call a service, not the database: " + ", ".join(offenders)


def test_side_menu_gates_by_permission_not_role_name():
    from cbpos.ui.widgets import side_menu

    source = inspect.getsource(side_menu)
    assert ".role.name.lower()" not in source and '"manager"' not in source


def test_no_dynamic_getattr_for_instance_attributes():
    """These attributes are set in __init__, so reading them through getattr(self, ...) hides typos."""
    import cbpos.ui.dialogs.product_editor as pe
    import cbpos.ui.views.admin_tools_view as at
    import cbpos.ui.views.credit_book_view as cb
    import cbpos.ui.views.login_view as lv
    import cbpos.ui.views.management_view as mv
    import cbpos.ui.views.sales_view as sv

    forbidden_patterns = [
        (sv, 'getattr(self, "_processing"'),
        (sv, 'getattr(self, "_pending_proforma_id"'),
        (lv, 'getattr(self, "_logo_source"'),
        (lv, 'getattr(self, "_logo_side"'),
        (lv, 'getattr(self, "_btn_size"'),
        (at, 'getattr(self, "_current_log_entries"'),
        (at, 'getattr(self, "_printer_worker"'),
        (at, 'getattr(self, "_drawer_worker"'),
        (mv, 'getattr(self, "user"'),
        (cb, 'getattr(self, "_showing_all_dates"'),
        (pe, 'getattr(self, "current_image_path"'),
    ]
    for module, pattern in forbidden_patterns:
        assert pattern not in inspect.getsource(module), f"{module.__name__}: {pattern}"
