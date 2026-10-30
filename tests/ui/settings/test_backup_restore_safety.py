"""#628: restore never replaces the database without (a) a safety
snapshot that can itself be restored and (b) an archive that really is a
CB POS backup with a healthy database inside.

The snapshot used to be made with a throwaway random password (so it
could never be opened), a failed snapshot was only logged, and any zip
with a file named cbpos.db -- or an unencrypted zip of anything -- could
overwrite the shop's data.
"""

import zipfile
from unittest.mock import patch

import pytest
import pyzipper

from cbpos.core.services.backup_service import BackupError, BackupService
from cbpos.core.services.config_service import ConfigService
from cbpos.i18n import translate_in
from cbpos.ui.workers import RestoreWorker
from tests.helpers.backup_helpers import data_dir, isolate_config_service, make_pos_db, read_marker

SHOP_PASSWORD = "shop-secret-42"


@pytest.fixture
def env(tmp_path, monkeypatch):
    isolate_config_service(monkeypatch, tmp_path)
    ConfigService.set_backup_password(SHOP_PASSWORD)
    make_pos_db(tmp_path / "cbpos.db", marker="live data")
    return tmp_path


def _encrypted_zip(path, members: dict[str, bytes], password: str = SHOP_PASSWORD) -> str:
    with pyzipper.AESZipFile(path, "w", compression=pyzipper.ZIP_DEFLATED, encryption=pyzipper.WZ_AES) as zf:
        zf.setpassword(password.encode())
        for name, data in members.items():
            zf.writestr(name, data)
    return str(path)


def _assert_db_untouched(env):
    assert read_marker(env / "cbpos.db") == "live data"


class TestRejectsArchivesThatAreNotPosBackups:
    def test_zip_without_cbpos_db(self, env):
        path = _encrypted_zip(env / "photos.zip", {"holiday.jpg": b"\xff\xd8 not a db"})

        with data_dir(env), pytest.raises(BackupError) as exc:
            BackupService.restore_backup(path, SHOP_PASSWORD, snapshot_dir=str(env / "snaps"))

        assert exc.value.code == "not_a_backup"
        _assert_db_untouched(env)

    def test_cbpos_db_that_is_not_a_database(self, env):
        path = _encrypted_zip(env / "fake.zip", {"cbpos.db": b"just some text, not sqlite" * 50})

        with data_dir(env), pytest.raises(BackupError) as exc:
            BackupService.restore_backup(path, SHOP_PASSWORD, snapshot_dir=str(env / "snaps"))

        assert exc.value.code == "db_invalid"
        _assert_db_untouched(env)

    def test_sqlite_db_from_another_app(self, env):
        import sqlite3

        other = env / "other.db"
        conn = sqlite3.connect(other)
        conn.execute("CREATE TABLE notes (id INTEGER PRIMARY KEY, body TEXT)")
        conn.commit()
        conn.close()
        path = _encrypted_zip(env / "other.zip", {"cbpos.db": other.read_bytes()})

        with data_dir(env), pytest.raises(BackupError) as exc:
            BackupService.restore_backup(path, SHOP_PASSWORD, snapshot_dir=str(env / "snaps"))

        assert exc.value.code == "not_a_backup"
        _assert_db_untouched(env)

    def test_file_that_is_not_a_zip(self, env):
        path = env / "notes.zip"
        path.write_bytes(b"definitely not a zip file")

        with data_dir(env), pytest.raises(BackupError) as exc:
            BackupService.restore_backup(str(path), SHOP_PASSWORD, snapshot_dir=str(env / "snaps"))

        assert exc.value.code == "not_a_backup"
        _assert_db_untouched(env)

    def test_plain_unencrypted_zip_is_still_validated(self, env):
        path = env / "plain.zip"
        with zipfile.ZipFile(path, "w") as zf:
            zf.writestr("readme.txt", "hello")

        with data_dir(env), pytest.raises(BackupError):
            BackupService.restore_backup(str(path), SHOP_PASSWORD, snapshot_dir=str(env / "snaps"))

        _assert_db_untouched(env)

    def test_wrong_password(self, env):
        with data_dir(env):
            path = BackupService.create_backup(str(env / "backups"), "another-password")

        with data_dir(env), pytest.raises(BackupError) as exc:
            BackupService.restore_backup(path, SHOP_PASSWORD, snapshot_dir=str(env / "snaps"))

        assert exc.value.code == "wrong_password"
        _assert_db_untouched(env)


class TestSafetySnapshot:
    def test_snapshot_is_restorable_with_the_shop_password(self, env):
        snaps = env / "snaps"
        with data_dir(env):
            backup = BackupService.create_backup(str(env / "backups"), SHOP_PASSWORD)
        # Change live data after the backup, then restore the backup.
        (env / "cbpos.db").unlink()
        make_pos_db(env / "cbpos.db", marker="changed after backup")

        with data_dir(env):
            BackupService.restore_backup(backup, SHOP_PASSWORD, snapshot_dir=str(snaps))
        assert read_marker(env / "cbpos.db") == "live data"

        snapshots = list(snaps.glob("*.pre_restore.zip"))
        assert len(snapshots) == 1
        assert BackupService.verify_backup(str(snapshots[0]), SHOP_PASSWORD)["valid"] is True

        # Undo the restore from the snapshot.
        with data_dir(env):
            BackupService.restore_backup(str(snapshots[0]), SHOP_PASSWORD, snapshot_dir=str(env / "snaps2"))
        assert read_marker(env / "cbpos.db") == "changed after backup"

    def test_snapshot_failure_aborts_the_restore(self, env):
        with data_dir(env):
            backup = BackupService.create_backup(str(env / "backups"), SHOP_PASSWORD)
        (env / "cbpos.db").unlink()
        make_pos_db(env / "cbpos.db", marker="live data")  # same marker, new file
        before = (env / "cbpos.db").read_bytes()

        real_create = BackupService.create_backup

        def failing_snapshot(destination_dir, password, kind="manual"):
            if kind == "snapshot":
                raise OSError("disk full")
            return real_create(destination_dir, password, kind)

        with (
            data_dir(env),
            patch.object(BackupService, "create_backup", side_effect=failing_snapshot),
            pytest.raises(BackupError) as exc,
        ):
            BackupService.restore_backup(backup, SHOP_PASSWORD, snapshot_dir=str(env / "snaps"))

        assert exc.value.code == "snapshot_failed"
        assert (env / "cbpos.db").read_bytes() == before

    def test_restore_worker_reports_refusal_code(self, env, qapp):
        path = _encrypted_zip(env / "photos.zip", {"holiday.jpg": b"not a db"})
        worker = RestoreWorker(path, SHOP_PASSWORD)
        refused, errors = [], []
        worker.refused.connect(refused.append)
        worker.error.connect(errors.append)

        with data_dir(env):
            worker.run()

        assert refused == ["not_a_backup"]
        assert errors == []
        _assert_db_untouched(env)

    def test_every_refusal_code_has_a_translation(self):
        for code in (
            "no_password",
            "not_a_backup",
            "wrong_password",
            "db_invalid",
            "corrupt",
            "snapshot_failed",
            "db_in_use",
            "not_found",
            "newer_version",
        ):
            for lang in ("en", "si", "ta"):
                assert translate_in(lang, f"data_safety.error_{code}") != f"data_safety.error_{code}"

    def test_no_shop_password_means_no_restore(self, env, monkeypatch):
        with data_dir(env):
            backup = BackupService.create_backup(str(env / "backups"), "an-old-password")
        (env / ".backup_password").unlink()
        before = (env / "cbpos.db").read_bytes()

        with data_dir(env), pytest.raises(BackupError) as exc:
            BackupService.restore_backup(backup, "an-old-password", snapshot_dir=str(env / "snaps"))

        assert exc.value.code == "no_password"
        assert (env / "cbpos.db").read_bytes() == before

    def test_issue_874_restore_refuses_unknown_revision(self, env):
        """A backup whose database is stamped at an unknown Alembic revision is refused."""
        import sqlite3

        future_db = env / "future_cbpos.db"
        make_pos_db(future_db, marker="future")
        conn = sqlite3.connect(future_db)
        conn.execute("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL PRIMARY KEY)")
        conn.execute("INSERT INTO alembic_version (version_num) VALUES ('f9e8d7c6b5a4')")
        conn.commit()
        conn.close()

        backup = _encrypted_zip(
            env / "future_backup.zip",
            {"cbpos.db": future_db.read_bytes(), "settings.json": b"{}"},
        )
        before = (env / "cbpos.db").read_bytes()

        with data_dir(env), pytest.raises(BackupError) as exc:
            BackupService.restore_backup(backup, SHOP_PASSWORD, snapshot_dir=str(env / "snaps"))

        assert exc.value.code == "newer_version"
        assert (env / "cbpos.db").read_bytes() == before

    def test_issue_874_verify_backup_reports_newer_version(self, env):
        """verify_backup(deep=True) reports newer_version for future revision."""
        import sqlite3

        future_db = env / "future_cbpos2.db"
        make_pos_db(future_db, marker="future")
        conn = sqlite3.connect(future_db)
        conn.execute("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL PRIMARY KEY)")
        conn.execute("INSERT INTO alembic_version (version_num) VALUES ('f9e8d7c6b5a4')")
        conn.commit()
        conn.close()

        backup = _encrypted_zip(
            env / "future_backup2.zip",
            {"cbpos.db": future_db.read_bytes(), "settings.json": b"{}"},
        )
        result = BackupService.verify_backup(backup, SHOP_PASSWORD, deep=True)

        assert result["valid"] is False
        assert result["error_code"] == "newer_version"

    def test_issue_839_data_safety_tabs_network_mode_notices(self, qapp, monkeypatch):
        """Data Safety tabs show notice card instead of actions in network mode."""
        from cbpos.ui.views.data_safety.backup_tab import BackupTabWidget
        from cbpos.ui.views.data_safety.maintenance_tab import MaintenanceTabWidget
        from cbpos.ui.views.data_safety.restore_tab import RestoreTabWidget
        from cbpos.ui.widgets.loading_overlay import LoadingOverlay

        # Network mode: is_supported = False
        monkeypatch.setattr(BackupService, "is_supported", staticmethod(lambda: False))
        monkeypatch.setattr(BackupService, "network_host", staticmethod(lambda: "pos-db.store.lan"))

        from PyQt6.QtWidgets import QWidget

        root = QWidget()
        overlay = LoadingOverlay(root)

        backup_tab = BackupTabWidget(overlay)
        restore_tab = RestoreTabWidget(overlay)
        maintenance_tab = MaintenanceTabWidget(overlay)

        # Check visibility in network mode
        assert backup_tab.standalone_container.isHidden()
        assert not backup_tab.notice_card.isHidden()
        assert "Backups are made on the database server" in backup_tab.notice_card.lbl_title.text()
        assert "pos-db.store.lan" in backup_tab.notice_card.lbl_body.text()

        assert restore_tab.standalone_container.isHidden()
        assert not restore_tab.notice_card.isHidden()

        assert maintenance_tab.grp_info.isHidden()
        assert maintenance_tab.grp_actions.isHidden()
        assert not maintenance_tab.notice_card.isHidden()

        # Switch back to standalone mode: is_supported = True
        monkeypatch.setattr(BackupService, "is_supported", staticmethod(lambda: True))
        backup_tab.refresh()
        restore_tab.refresh_password_hint()
        maintenance_tab.refresh()

        assert not backup_tab.standalone_container.isHidden()
        assert backup_tab.notice_card.isHidden()

        assert not restore_tab.standalone_container.isHidden()
        assert restore_tab.notice_card.isHidden()

        assert not maintenance_tab.grp_info.isHidden()
        assert not maintenance_tab.grp_actions.isHidden()
        assert maintenance_tab.notice_card.isHidden()

        # Translations parity check
        for lang in ("en", "si", "ta"):
            for key in ("network_mode_title", "network_mode_body", "error_network_mode"):
                text = translate_in(lang, f"data_safety.{key}")
                assert text != f"data_safety.{key}"
                if key == "network_mode_body":
                    assert "{host}" in text
