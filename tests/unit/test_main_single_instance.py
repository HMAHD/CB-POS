"""main() startup order (#691): ``--migrate-only`` skips the single-instance
guard and splash; a second launch exits before any slow startup work.
"""

import sys
from unittest.mock import MagicMock

import pytest

import main
from cbpos.infrastructure import single_instance


def _fail(what: str):
    def _raise(*_a, **_k):
        raise AssertionError(f"{what} must not run here")

    return _raise


def test_migrate_only_skips_single_instance_and_splash(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["cbpos", "--migrate-only"])
    monkeypatch.setattr(main, "ensure_data_dir", lambda: None)
    monkeypatch.setattr(main, "run_migrations", lambda: None)
    monkeypatch.setattr(main, "QApplication", _fail("QApplication"))
    monkeypatch.setattr(single_instance, "acquire", _fail("single-instance guard"))
    monkeypatch.setattr("cbpos.ui.startup_splash.create_startup_splash", _fail("splash"))

    with pytest.raises(SystemExit) as exc:
        main.main()
    assert exc.value.code == 0


def test_second_launch_exits_before_startup_work(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["cbpos"])
    monkeypatch.setattr(sys, "excepthook", sys.excepthook)
    monkeypatch.setattr(main, "QApplication", MagicMock())
    monkeypatch.setattr(main, "qInstallMessageHandler", lambda _h: None)
    monkeypatch.setenv("QT_AUTO_SCREEN_SCALE_FACTOR", "1")  # restored after the test
    monkeypatch.setattr("cbpos.infrastructure.app_identity.set_windows_app_user_model_id", lambda: False)
    monkeypatch.setattr(single_instance, "acquire", lambda: None)
    monkeypatch.setattr(main, "ensure_data_dir", _fail("ensure_data_dir"))
    monkeypatch.setattr(main, "run_migrations", _fail("run_migrations"))
    monkeypatch.setattr(main, "setup_logging", _fail("setup_logging"))
    monkeypatch.setattr("cbpos.ui.startup_splash.create_startup_splash", _fail("splash"))

    with pytest.raises(SystemExit) as exc:
        main.main()
    assert exc.value.code == 0


def test_close_splash_is_safe_without_splash(monkeypatch):
    monkeypatch.setattr(main, "_splash", None)
    main._close_splash()

    splash = MagicMock()
    monkeypatch.setattr(main, "_splash", splash)
    main._close_splash()
    splash.close.assert_called_once()
    assert main._splash is None
