"""Tests for Issue #880: Report view permissions and export permission for Print/Email."""

import pytest
from sqlalchemy import select

from cbpos.core.constants.permissions import Permissions
from cbpos.core.models import Permission, Role, User
from cbpos.core.reports.registry import ReportRegistry
from cbpos.core.services.auth_service import AuthService
from cbpos.core.services.report_service import ReportService
from cbpos.ui.views.reports.report_viewer import ReportViewer


def _create_user_with_permissions(db_session, username: str, perms: list[str]) -> User:
    role = Role(name=f"Role_{username}")
    db_session.add(role)
    db_session.flush()

    for code in perms:
        perm = db_session.execute(select(Permission).where(Permission.code == code)).scalar_one_or_none()
        if not perm:
            perm = Permission(code=code)
            db_session.add(perm)
            db_session.flush()
        role.permissions.append(perm)

    user = User(username=username, pin_hash=AuthService.hash_pin("1234"), role=role, is_active=True)
    db_session.add(user)
    db_session.commit()
    return user


def test_issue_880_role_without_view_profit_cannot_list_or_run_pnl(db_session):
    """A role without reports.view_profit cannot see profit_loss in available_reports, and cannot run it."""
    from cbpos.core.reports import register_all_reports

    register_all_reports()

    cashier = _create_user_with_permissions(db_session, "cashier_880", [Permissions.REPORTS_VIEW_SALES])
    manager = _create_user_with_permissions(
        db_session, "manager_880", [Permissions.REPORTS_VIEW_SALES, Permissions.REPORTS_VIEW_PROFIT]
    )

    # 1. available_reports for cashier must NOT include profit_loss
    cashier_reports = ReportService.available_reports(cashier)
    cashier_ids = {r.id for r in cashier_reports}
    assert "profit_loss" not in cashier_ids

    # available_reports for manager MUST include profit_loss
    manager_reports = ReportService.available_reports(manager)
    manager_ids = {r.id for r in manager_reports}
    assert "profit_loss" in manager_ids

    # 2. Running profit_loss as cashier must raise PermissionError
    with pytest.raises(PermissionError, match=r"reports\.view_profit"):
        ReportService.run("profit_loss", {}, user=cashier)

    # 3. Running profit_loss as manager succeeds
    df = ReportService.run("profit_loss", {}, user=manager)
    assert df is not None


def test_issue_880_email_requires_export_permission(qtbot, monkeypatch):
    """Calling email_report or print_report without reports.export prompts for override, aborting if None."""
    viewer = ReportViewer()
    qtbot.addWidget(viewer)

    import pandas as pd

    viewer._full_df = pd.DataFrame({"col": [1, 2]})
    viewer.current_report = ReportRegistry().get_report_by_id("daily_sales")

    # Patch override to return None (user cancelled override prompt)
    override_called = []

    def mock_override(code, parent=None):
        override_called.append(code)
        return None

    monkeypatch.setattr("cbpos.core.utils.permission_helper.check_permission_with_override", mock_override)

    worker_started = []
    monkeypatch.setattr("cbpos.ui.views.reports.report_viewer.start_background_job", lambda w: worker_started.append(w))

    # Email
    viewer.email_report()
    assert Permissions.REPORTS_EXPORT in override_called
    assert len(worker_started) == 0

    # Print
    override_called.clear()
    viewer.print_report()
    assert Permissions.REPORTS_EXPORT in override_called
    assert len(worker_started) == 0
