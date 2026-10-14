"""main() tells the splash each real startup step, in order (#722).

Every step boundary calls ``set_startup_status`` with its key; a step that
doesn't run (no migration to apply, no LAN Sync) has no message.
"""

import sys
from unittest.mock import MagicMock

import pytest

import main
from cbpos.infrastructure import single_instance

_COMMON_HEAD = ["startup.checking_data"]
_COMMON_TAIL = [
    "startup.preparing_screen",
    "startup.setting_up_reports",
    "startup.loading_printing",
    "startup.loading_pdf",
    "startup.loading_screens",
    "startup.preparing_counter",
]


@pytest.fixture
def run_main(monkeypatch, tmp_path):
    """Run main() with every heavy or global side effect stubbed out.

    Returns a function taking the settings and whether a migration is
    pending, and returning the status keys main() sent, in order.
    """

    def _run(settings: dict, migration_pending: bool) -> list[str]:
        seen: list[str] = []

        def _fake_migrations(status=None):
            if status is not None:
                status("startup.checking_data")
                if migration_pending:
                    status("startup.updating_data")
            return None

        monkeypatch.setattr(sys, "argv", ["cbpos"])
        monkeypatch.setattr(sys, "excepthook", sys.excepthook)
        monkeypatch.setenv("QT_AUTO_SCREEN_SCALE_FACTOR", "1")
        monkeypatch.setattr(main, "QApplication", MagicMock())
        monkeypatch.setattr(main, "QGuiApplication", MagicMock())
        monkeypatch.setattr(main, "qInstallMessageHandler", lambda _h: None)
        monkeypatch.setattr(main, "ensure_data_dir", lambda: None)
        monkeypatch.setattr(main, "setup_logging", lambda: None)
        monkeypatch.setattr(main, "run_migrations", _fake_migrations)
        monkeypatch.setattr(main.ResourceLoader, "load_fonts", staticmethod(lambda: "Arial"))
        monkeypatch.setattr(main.ResourceLoader, "get_font_families", staticmethod(lambda: ["Arial"]))
        monkeypatch.setattr("cbpos.infrastructure.app_identity.set_windows_app_user_model_id", lambda: False)
        monkeypatch.setattr("cbpos.infrastructure.app_identity.apply_app_icon", lambda _app: None)
        monkeypatch.setattr(single_instance, "acquire", lambda: MagicMock())
        monkeypatch.setattr("cbpos.i18n.set_language", lambda _lang: None)
        monkeypatch.setattr("cbpos.i18n.register_language_callback", lambda *_a, **_k: None)
        monkeypatch.setattr("cbpos.ui.startup_splash.create_startup_splash", lambda: MagicMock())
        monkeypatch.setattr("cbpos.ui.startup_splash.set_startup_status", seen.append)
        monkeypatch.setattr("cbpos.infrastructure.input_manager.InputManager", MagicMock())

        from cbpos.core.services.config_service import ConfigService
        from cbpos.core.services.theme_service import ThemeService

        settings_file = tmp_path / "settings.json"
        settings_file.write_text("{}")
        monkeypatch.setattr(ConfigService, "SETTINGS_FILE", str(settings_file))
        monkeypatch.setattr(ConfigService, "get", staticmethod(lambda key, *_a: settings.get(key)))
        monkeypatch.setattr(ThemeService, "set_stylesheet_handler", staticmethod(lambda _h: None))
        monkeypatch.setattr(ThemeService, "apply_theme", staticmethod(lambda _t: None))
        monkeypatch.setattr("cbpos.core.reports.register_all_reports", lambda: None)
        monkeypatch.setattr(
            "cbpos.core.services.database_setup_service.DatabaseSetupService.needs_setup",
            staticmethod(lambda: False),
        )
        monkeypatch.setattr("cbpos.core.utils.permission_helper.set_override_handler", lambda _h: None)

        # Every MainWindow import stage counts as not loaded yet; the real
        # MainWindow is swapped for a stub.
        monkeypatch.setattr(main, "_is_imported", lambda _module: False)
        import cbpos.ui.main_window

        monkeypatch.setattr(cbpos.ui.main_window, "MainWindow", MagicMock())
        monkeypatch.setattr("cbpos.infrastructure.sync_server.SyncServer", MagicMock())
        monkeypatch.setattr("cbpos.infrastructure.sync_client.SyncClient", MagicMock())
        monkeypatch.setattr("PyQt6.QtCore.QTimer.singleShot", lambda *_a: None)

        main.QApplication.return_value.exec.return_value = 0
        with pytest.raises(SystemExit) as exc:
            main.main()
        assert exc.value.code == 0
        return seen

    yield _run
    main._splash = None


def test_standalone_without_migration_skips_both_optional_steps(run_main):
    seen = run_main({"terminal_mode": "standalone"}, migration_pending=False)
    assert seen == _COMMON_HEAD + _COMMON_TAIL


def test_pending_migration_adds_the_updating_step(run_main):
    seen = run_main({}, migration_pending=True)
    assert seen == ["startup.checking_data", "startup.updating_data", *_COMMON_TAIL]


def test_terminal_says_it_is_connecting_to_the_main_pc(run_main):
    settings = {"terminal_mode": "terminal", "sync_shared_secret": "s3cret", "main_pc_address": "10.0.0.2:5555"}
    seen = run_main(settings, migration_pending=False)
    assert seen == _COMMON_HEAD + _COMMON_TAIL + ["startup.connecting_main_pc"]


def test_main_pc_says_it_is_starting_sync(run_main):
    settings = {"terminal_mode": "main", "sync_shared_secret": "s3cret"}
    seen = run_main(settings, migration_pending=False)
    assert seen == _COMMON_HEAD + _COMMON_TAIL + ["startup.starting_sync"]


@pytest.mark.parametrize(
    "settings",
    [
        {"terminal_mode": "terminal", "sync_shared_secret": "", "main_pc_address": "10.0.0.2:5555"},
        {"terminal_mode": "terminal", "sync_shared_secret": "s3cret", "main_pc_address": ""},
        {"terminal_mode": "main", "sync_shared_secret": ""},
    ],
)
def test_misconfigured_lan_sync_starts_nothing_so_says_nothing(run_main, settings):
    seen = run_main(settings, migration_pending=False)
    assert seen == _COMMON_HEAD + _COMMON_TAIL


def test_an_already_loaded_stage_is_not_announced(monkeypatch):
    """A stage some earlier step already imported is skipped, never named."""
    seen: list[str] = []
    loaded = {"cbpos.core.services.printer_service"}
    monkeypatch.setattr(main, "_is_imported", lambda module: module in loaded)
    monkeypatch.setattr(main.importlib, "import_module", lambda _name: MagicMock())
    main._load_main_window_class(seen.append)
    assert seen == ["startup.loading_pdf", "startup.loading_screens"]
