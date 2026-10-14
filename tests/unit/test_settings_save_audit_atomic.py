"""
#729: Saving Settings wrote its Activity Log row from the view, in its own session, *before* the
settings were saved -- so a save that failed still left a logged tax change that never happened.
The audit row is now written by the service, together with the save, and only if the save worked.

Settings live in settings.json, so the only thing faked here is the disk write.
"""

import json
from types import SimpleNamespace

import pytest
from PyQt6.QtWidgets import QMessageBox

from cbpos.core.models import AuditLog, Role, User
from cbpos.core.services.auth_service import AuthService
from cbpos.core.services.config_service import ConfigService
from cbpos.core.utils.audit_format import format_audit_details
from cbpos.i18n import _t, get_language, set_language

pytestmark = pytest.mark.usefixtures("qapp")

SAVED = {
    "language": "en",
    "theme": "Dark",
    "font_size": 12,
    "vat_registered": True,
    "tax_vat_rate": 18.0,
    "tax_sscl_rate": 2.5,
    "tax_sscl_turnover_pct": 50.0,
    "terminal_id": "TERM-01",
}


@pytest.fixture(autouse=True)
def english():
    original = get_language()
    set_language("en")
    yield
    set_language(original)


@pytest.fixture
def signed_in(db_session, monkeypatch):
    role = Role(name="AuditTestRole729", access_level=1)
    db_session.add(role)
    db_session.flush()
    user = User(username="audit729", pin_hash=AuthService.hash_pin("1234"), role_id=role.id, is_active=True)
    db_session.add(user)
    db_session.flush()
    monkeypatch.setattr(AuthService, "get_current_user", lambda: SimpleNamespace(id=user.id))
    return user


@pytest.fixture
def settings_file(tmp_path, monkeypatch):
    """The real ConfigService, reading and writing a settings.json of its own."""
    monkeypatch.setattr(ConfigService, "SETTINGS_FILE", str(tmp_path / "settings.json"))
    monkeypatch.setattr(ConfigService, "_settings", dict(SAVED))
    return tmp_path / "settings.json"


@pytest.fixture
def disk_full(monkeypatch):
    def fail(*_args, **_kwargs):
        raise OSError("No space left on device")

    monkeypatch.setattr(ConfigService, "_write_restricted", fail)


@pytest.fixture
def errors_shown(monkeypatch) -> list[str]:
    shown: list[str] = []
    monkeypatch.setattr(QMessageBox, "critical", lambda _parent, _title, text, *a, **k: shown.append(text))
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: QMessageBox.StandardButton.Yes)
    return shown


@pytest.fixture
def settings_view(qapp, db_session, signed_in, settings_file, errors_shown, monkeypatch):
    from cbpos.ui.views.settings_view import SettingsView

    monkeypatch.setattr("cbpos.core.utils.permission_helper.check_permission_with_override", lambda p, w: True)
    view = SettingsView()
    yield view
    view.deleteLater()


def _tax_rows(session) -> list[AuditLog]:
    return session.query(AuditLog).filter_by(action="TAX_RATE_CHANGE").all()


class TestFailedSave:
    def test_failed_save_leaves_no_audit_row(self, settings_view, db_session, disk_full):
        before = len(_tax_rows(db_session))
        settings_view.pages[1].spin_vat.setValue(15)

        settings_view.save_all()

        assert len(_tax_rows(db_session)) == before

    def test_failed_save_changes_nothing_and_says_so(self, settings_view, disk_full, errors_shown):
        settings_view.pages[1].spin_vat.setValue(15)

        settings_view.save_all()

        assert ConfigService.get("tax_vat_rate") == 18.0
        assert errors_shown == [_t("settings.save_failed")]
        assert settings_view.lbl_status.property("state") == "unsaved"  # so the owner can retry


class TestSuccessfulSave:
    def test_one_readable_row_and_the_file_has_the_new_rate(self, settings_view, db_session, settings_file):
        before = len(_tax_rows(db_session))
        settings_view.pages[1].spin_vat.setValue(15)

        settings_view.save_all()

        rows = _tax_rows(db_session)
        assert len(rows) == before + 1
        assert format_audit_details(rows[-1].action, rows[-1].details) == "VAT rate changed from 18% to 15%"
        assert json.loads(settings_file.read_text(encoding="utf-8"))["tax_vat_rate"] == 15
