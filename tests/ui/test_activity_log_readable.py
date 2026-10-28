"""
#613: every Settings save logged a fake tax change (str(18.0) != str(18)), the audit row was
written from the view, and the Activity Log showed raw JSON, never showed the action, and
printed str(timestamp) with microseconds. Now: Decimal compare in a service, readable details
formatted at display time (raw JSON kept in the DB), translated action, local strftime time.
"""

import json
from datetime import UTC, datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from PyQt6.QtWidgets import QMessageBox

from cbpos.core.models import AuditLog, Role, User
from cbpos.core.services.auth_service import AuthService
from cbpos.core.services.config_service import ConfigService
from cbpos.core.services.settings_audit_service import SettingsAuditService
from cbpos.core.utils.audit_format import format_audit_action, format_audit_details, format_log_time
from cbpos.i18n import get_language, set_language

pytestmark = pytest.mark.usefixtures("qapp")


@pytest.fixture
def lang():
    original = get_language()
    yield set_language
    set_language(original)


class TestTaxDiff:
    def test_int_and_float_of_the_same_rate_are_no_change(self):
        old = {"tax_vat_rate": 18.0, "tax_sscl_rate": 2.5, "tax_sscl_turnover_pct": 50.0, "vat_registered": True}
        new = {"tax_vat_rate": 18, "tax_sscl_rate": 2.5, "tax_sscl_turnover_pct": 50, "vat_registered": True}
        assert SettingsAuditService.tax_changes(old, new) == {}

    def test_real_change_is_reported(self):
        changes = SettingsAuditService.tax_changes({"tax_vat_rate": 18.0}, {"tax_vat_rate": 15})
        assert changes == {"tax_vat_rate": {"old": 18.0, "new": 15}}

    def test_bool_toggle_is_reported(self):
        changes = SettingsAuditService.tax_changes({"vat_registered": False}, {"vat_registered": True})
        assert changes == {"vat_registered": {"old": False, "new": True}}

    def test_keys_missing_from_the_new_settings_are_ignored(self):
        assert SettingsAuditService.tax_changes({"tax_vat_rate": 18}, {}) == {}


class TestDisplayFormatting:
    def test_vat_change_reads_as_a_sentence(self, lang):
        lang("en")
        details = json.dumps({"tax_vat_rate": {"old": 18.0, "new": 15}})
        assert format_audit_details("TAX_RATE_CHANGE", details) == "VAT rate changed from 18% to 15%"

    def test_several_changes_and_the_vat_switch(self, lang):
        lang("en")
        details = json.dumps(
            {"tax_sscl_rate": {"old": 2.5, "new": 2.75}, "vat_registered": {"old": False, "new": True}}
        )
        text = format_audit_details("TAX_RATE_CHANGE", details)
        assert text == "SSCL rate changed from 2.5% to 2.75%; VAT registration turned on"

    @pytest.mark.parametrize("language", ["si", "ta"])
    def test_translated(self, lang, language):
        lang(language)
        details = json.dumps({"tax_vat_rate": {"old": 18.0, "new": 15}})
        text = format_audit_details("TAX_RATE_CHANGE", details)
        assert "changed" not in text and "18" in text and "15" in text and "{" not in text

    def test_plain_text_details_shown_as_stored(self):
        assert format_audit_details("VOID_SALE", "Voided sale S-1. Reason: x") == "Voided sale S-1. Reason: x"
        assert format_audit_details("VOID_SALE", None) == ""

    @pytest.mark.parametrize("language", ["en", "si", "ta"])
    def test_actions_are_translated(self, lang, language):
        lang(language)
        for action in ("TAX_RATE_CHANGE", "User Login", "Session Timeout", "VOID_SALE", "UPDATE_PERMISSIONS"):
            label = format_audit_action(action)
            assert label and label != action and "_" not in label
        assert format_audit_action("SOMETHING_NEW") == "SOMETHING_NEW"

    def test_naive_timestamps_are_local_already_and_drop_microseconds(self):
        # AuditLog.timestamp defaults to datetime.now (naive local time), never UTC
        assert AuditLog.__table__.c.timestamp.default.arg.__name__ == "now"
        assert format_log_time(datetime(2026, 10, 7, 16, 52, 3, 123456)) == "2026-10-07 16:52:03"

    def test_aware_timestamps_are_converted_to_local_time(self):
        utc_time = datetime(2026, 10, 7, 4, 52, tzinfo=UTC)
        local = utc_time.astimezone()  # this machine's zone
        assert format_log_time(utc_time) == local.strftime("%Y-%m-%d %H:%M:%S")
        plus_530 = datetime(2026, 10, 7, 10, 22, tzinfo=timezone(timedelta(hours=5, minutes=30)))
        assert format_log_time(plus_530) == local.strftime("%Y-%m-%d %H:%M:%S")

    def test_missing_timestamp(self):
        assert format_log_time(None) == ""


# ---------------------------------------------------------------------------
# Settings save -> audit rows
# ---------------------------------------------------------------------------


class _FakeConfigStore:
    def __init__(self, initial: dict):
        self._data = dict(initial)

    def get(self, key):
        return self._data.get(key)

    def get_all(self):
        return dict(self._data)

    def set(self, key, value):
        self._data[key] = value

    def update_all(self, data, **_kwargs):
        self._data.update(data)


@pytest.fixture
def settings_view(qapp, db_session, monkeypatch):
    from cbpos.ui.views.settings_view import SettingsView

    store = _FakeConfigStore(
        {
            "language": "en",
            "theme": "Dark",
            "font_size": 12,
            "vat_registered": True,
            "tax_vat_rate": 18.0,  # float, as written by the defaults
            "tax_sscl_rate": 2.5,
            "tax_sscl_turnover_pct": 50.0,
            "terminal_id": "TERM-01",
        }
    )
    for name in ("get", "get_all", "set", "update_all"):
        monkeypatch.setattr(ConfigService, name, getattr(store, name))
    monkeypatch.setattr("cbpos.core.utils.permission_helper.check_permission_with_override", lambda p, w: True)
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: QMessageBox.StandardButton.Yes)

    role = Role(name="AuditTestRole613", access_level=1)
    db_session.add(role)
    db_session.flush()
    user = User(username="audit613", pin_hash=AuthService.hash_pin("1234"), role_id=role.id, is_active=True)
    db_session.add(user)
    db_session.flush()
    monkeypatch.setattr(AuthService, "get_current_user", lambda: SimpleNamespace(id=user.id))

    view = SettingsView()
    yield view, db_session
    view.deleteLater()


def _tax_rows(session) -> list[AuditLog]:
    return session.query(AuditLog).filter_by(action="TAX_RATE_CHANGE").all()


class TestSettingsSaveAudit:
    def test_saving_without_changes_writes_no_audit_row(self, settings_view):
        view, session = settings_view
        before = len(_tax_rows(session))
        view.save_all()
        view.save_all()
        assert len(_tax_rows(session)) == before

    def test_changing_vat_writes_exactly_one_readable_row(self, settings_view, lang):
        lang("en")
        view, session = settings_view
        before = len(_tax_rows(session))
        view.pages[1].spin_vat.setValue(15)

        view.save_all()

        rows = _tax_rows(session)
        assert len(rows) == before + 1
        row = rows[-1]
        assert json.loads(row.details) == {"tax_vat_rate": {"old": 18.0, "new": 15}}  # raw JSON kept
        assert row.terminal_id == "TERM-01"
        assert format_audit_details(row.action, row.details) == "VAT rate changed from 18% to 15%"

    def test_view_no_longer_writes_audit_rows_itself(self):
        import inspect

        from cbpos.ui.views import settings_view

        source = inspect.getsource(settings_view)
        assert "AuditLog" not in source and "Database" not in source


class TestActivityLogTable:
    def test_row_shows_local_time_translated_action_and_readable_details(self, db_session, qtbot, lang):
        from cbpos.ui.views.user_view import UserView

        lang("en")
        log = SimpleNamespace(
            timestamp=datetime(2026, 10, 7, 16, 52, 3, 999999),
            user=SimpleNamespace(username="admin"),
            event_type="SECURITY",
            action="TAX_RATE_CHANGE",
            terminal_id="TERM-01",
            details=json.dumps({"tax_vat_rate": {"old": 18.0, "new": 15}}),
        )
        with patch("cbpos.ui.views.user_view.UserService.get_recent_activity", return_value=[log]):
            view = UserView()
            qtbot.addWidget(view)
            view.load_logs()

        headers = [view.log_table.horizontalHeaderItem(i).text() for i in range(view.log_table.columnCount())]
        assert headers == ["Time", "User", "Event", "Action", "Terminal", "Details"]
        row = [view.log_table.item(0, c).text() for c in range(6)]
        assert row == [
            "2026-10-07 16:52:03",
            "admin",
            "Security",
            "Tax settings changed",
            "TERM-01",
            "VAT rate changed from 18% to 15%",
        ]
