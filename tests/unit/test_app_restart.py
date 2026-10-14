"""
Restart helper (#581): relaunches CB POS with the right command for a frozen
exe vs a source checkout, closes through the normal close path first, and
never relaunches if the close is refused. Nothing here really restarts --
QProcess.startDetached and QApplication.quit are always mocked.
"""

import os
import sys
from unittest.mock import MagicMock

import pytest

from cbpos.config import Config
from cbpos.infrastructure import single_instance
from cbpos.ui import app_restart


@pytest.fixture
def fakes(monkeypatch):
    calls: dict = {"start": [], "quit": 0, "dispose": 0, "stop_timer": 0, "release": 0, "restart_env": []}

    def _start(program, args):
        calls["start"].append((program, list(args)))
        calls["restart_env"].append(os.environ.get(single_instance.RESTART_ENV_VAR))
        return (True, 1234)

    def _quit():
        calls["quit"] += 1

    monkeypatch.setattr(app_restart.QProcess, "startDetached", staticmethod(_start))
    monkeypatch.setattr(app_restart.QApplication, "quit", staticmethod(_quit))

    fake_db = MagicMock()
    fake_db.return_value.engine.dispose.side_effect = lambda: calls.__setitem__("dispose", calls["dispose"] + 1)
    monkeypatch.setattr("cbpos.core.database.Database", fake_db)
    monkeypatch.setattr(
        "cbpos.core.services.scheduler_service.SchedulerService.stop_timer",
        lambda: calls.__setitem__("stop_timer", calls["stop_timer"] + 1),
    )
    monkeypatch.delenv("PYINSTALLER_RESET_ENVIRONMENT", raising=False)
    monkeypatch.delenv(single_instance.RESTART_ENV_VAR, raising=False)
    monkeypatch.setattr(single_instance, "release", lambda: calls.__setitem__("release", calls["release"] + 1))
    return calls


def test_dev_command_relaunches_main_py_with_current_interpreter(monkeypatch):
    monkeypatch.delattr(sys, "frozen", raising=False)
    program, args = app_restart.restart_command()
    assert program == sys.executable
    assert args == [str(Config.BASE_DIR / "main.py")]


def test_frozen_command_relaunches_the_exe_with_no_args(monkeypatch):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", r"C:\Program Files\CB POS\cbpos.exe")
    assert app_restart.restart_command() == (r"C:\Program Files\CB POS\cbpos.exe", [])


def test_restart_closes_window_then_starts_new_instance_and_quits(fakes, monkeypatch):
    monkeypatch.delattr(sys, "frozen", raising=False)
    order: list[str] = []
    window = MagicMock()
    window.close.side_effect = lambda: order.append("close") or True

    assert app_restart.restart_application(window) is True

    assert order == ["close"]
    window.watchdog.stop_monitoring.assert_called_once()
    assert fakes["stop_timer"] == 1
    assert fakes["dispose"] == 1
    assert fakes["start"] == [(sys.executable, [str(Config.BASE_DIR / "main.py")])]
    assert fakes["quit"] == 1
    assert "PYINSTALLER_RESET_ENVIRONMENT" not in os.environ


def test_frozen_restart_asks_pyinstaller_for_a_fresh_environment(fakes, monkeypatch):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", "/opt/cbpos/cbpos")
    window = MagicMock()
    window.close.return_value = True

    assert app_restart.restart_application(window) is True
    assert fakes["start"] == [("/opt/cbpos/cbpos", [])]
    assert os.environ.get("PYINSTALLER_RESET_ENVIRONMENT") == "1"


def test_refused_close_never_relaunches(fakes):
    window = MagicMock()
    window.close.return_value = False

    assert app_restart.restart_application(window) is False
    assert fakes["start"] == []
    assert fakes["quit"] == 0


def test_restart_frees_single_instance_name_and_flags_child(fakes, monkeypatch):
    """The relaunched process must take over, not hand off to us (#691, #673)."""
    monkeypatch.delattr(sys, "frozen", raising=False)
    window = MagicMock()
    window.close.return_value = True

    assert app_restart.restart_application(window) is True
    assert fakes["release"] == 1
    assert fakes["restart_env"] == ["1"]  # visible to the child at spawn time
    assert single_instance.RESTART_ENV_VAR not in os.environ  # not leaked afterwards


def test_refused_close_keeps_single_instance(fakes):
    window = MagicMock()
    window.close.return_value = False
    assert app_restart.restart_application(window) is False
    assert fakes["release"] == 0
