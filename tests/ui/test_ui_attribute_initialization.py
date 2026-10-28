"""Tests for issue #703: initialize instance attributes in __init__ instead of using dynamic getattr."""

import pytest

import cbpos.core.models  # noqa: F401 - registers all ORM tables with Base.metadata

pytestmark = pytest.mark.usefixtures("qapp", "db_session")


def test_sales_view_attributes_initialized(qapp, db_session):
    from cbpos.ui.views.sales_view import SalesView

    view = SalesView()
    try:
        assert hasattr(view, "_processing")
        assert view._processing is False
        assert hasattr(view, "_pending_proforma_id")
        assert view._pending_proforma_id is None
    finally:
        view.deleteLater()


def test_login_view_attributes_initialized(qapp):
    from cbpos.ui.views.login_view import LoginView

    view = LoginView()
    try:
        assert hasattr(view, "_logo_source")
        assert hasattr(view, "_logo_side")
        assert hasattr(view, "_btn_size")
    finally:
        view.deleteLater()


def test_admin_tools_view_attributes_initialized(qapp, db_session):
    from cbpos.ui.views.admin_tools_view import AdminToolsView

    view = AdminToolsView()
    try:
        assert hasattr(view, "_current_log_entries")
        assert isinstance(view._current_log_entries, list)
        assert hasattr(view, "_printer_worker")
        assert view._printer_worker is None
        assert hasattr(view, "_drawer_worker")
        assert view._drawer_worker is None
    finally:
        view.deleteLater()


def test_management_view_attributes_initialized(qapp, db_session):
    from cbpos.ui.views.management_view import ManagementView

    view = ManagementView()
    try:
        assert hasattr(view, "user")
        assert view.user is None
    finally:
        view.deleteLater()


def test_credit_book_view_attributes_initialized(qapp, db_session):
    from cbpos.ui.views.credit_book_view import CreditBookView

    view = CreditBookView()
    try:
        assert hasattr(view, "_showing_all_dates")
        assert view._showing_all_dates is False
    finally:
        view.deleteLater()


def test_product_editor_attributes_initialized(qapp, db_session):
    from cbpos.ui.dialogs.product_editor import ProductEditor

    dlg = ProductEditor()
    try:
        assert hasattr(dlg, "current_image_path")
        assert dlg.current_image_path is None
    finally:
        dlg.deleteLater()


def test_no_dynamic_getattr_for_instance_attributes():
    """Verify that the target files do not use dynamic getattr(self, ...) for these attributes."""
    import inspect

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
        source = inspect.getsource(module)
        assert pattern not in source, f"Found forbidden dynamic getattr in {module.__name__}: {pattern}"
