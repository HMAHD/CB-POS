"""Single-instance guard (#691): a second launch hands off to the running one
and exits; a stale socket or a self-restart (#673) never blocks startup.

Every test uses a unique server name so nothing here can collide with a real
CB POS (or another test run) on the same machine.
"""

import sys
import threading
import uuid
from types import SimpleNamespace

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtNetwork import QLocalServer
from PyQt6.QtWidgets import QWidget

from cbpos.infrastructure import single_instance
from cbpos.infrastructure.single_instance import SingleInstance


@pytest.fixture
def name():
    key = f"cbpos-test-{uuid.uuid4().hex[:12]}"
    yield key
    QLocalServer.removeServer(key)


@pytest.fixture(autouse=True)
def _no_leftover_active(monkeypatch):
    monkeypatch.delenv(single_instance.RESTART_ENV_VAR, raising=False)
    yield
    single_instance.release()


def _notify_in_thread(key: str, result: dict) -> threading.Thread:
    """Blocking client calls must not run on the thread that serves the socket."""

    def _run():
        result["ok"] = SingleInstance(key).notify_running_instance(timeout_ms=2000)

    t = threading.Thread(target=_run)
    t.start()
    return t


def test_server_name_is_per_user_and_per_data_dir(tmp_path):
    a = single_instance.server_name(tmp_path, user="alice")
    assert a == single_instance.server_name(tmp_path, user="alice")
    assert a != single_instance.server_name(tmp_path, user="bob")
    assert a != single_instance.server_name(tmp_path / "other", user="alice")
    assert a.startswith("cbpos-") and len(a) <= 40


def test_notify_without_running_instance_returns_false(name, qapp):
    assert SingleInstance(name).notify_running_instance(timeout_ms=200) is False


def test_second_launch_asks_first_to_activate(name, qapp, qtbot):
    first = single_instance.acquire(name, restarted=False)
    assert first is not None and first.is_listening

    result: dict = {}
    with qtbot.waitSignal(first.activation_requested, timeout=5000):
        thread = _notify_in_thread(name, result)
    thread.join(5)
    assert result["ok"] is True


def test_acquire_returns_none_when_another_instance_runs(name, qapp, qtbot, monkeypatch):
    first = SingleInstance(name)
    assert first.listen()
    # The hand-off itself is covered above; here only acquire()'s decision.
    monkeypatch.setattr(SingleInstance, "notify_running_instance", lambda self, timeout_ms=1000: True)
    assert single_instance.acquire(name, restarted=False) is None
    first.close()


def test_stale_socket_is_cleared(name, qapp):
    if sys.platform == "win32":
        pytest.skip("named pipes vanish with their process; no stale file on Windows")
    # Leave a socket file behind without anyone serving it, like a crashed process.
    import socket
    import tempfile
    from pathlib import Path

    path = Path(tempfile.gettempdir()) / name
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.bind(str(path))
    sock.close()
    assert path.exists()

    instance = single_instance.acquire(name, restarted=False)
    assert instance is not None and instance.is_listening


def test_release_frees_the_name_for_the_relaunched_process(name, qapp):
    first = single_instance.acquire(name, restarted=False)
    assert first is not None and first.is_listening
    single_instance.release()
    assert not first.is_listening

    second = SingleInstance(name)
    assert second.notify_running_instance(timeout_ms=200) is False
    assert second.listen()
    second.close()


def test_restarted_launch_never_hands_off(name, qapp, monkeypatch):
    def _boom(self, timeout_ms=1000):
        raise AssertionError("a restarted launch must not hand off to the old instance")

    monkeypatch.setattr(SingleInstance, "notify_running_instance", _boom)
    monkeypatch.setenv(single_instance.RESTART_ENV_VAR, "1")

    instance = single_instance.acquire(name)
    assert instance is not None and instance.is_listening
    # Cleared so our own later restarts/children don't inherit it.
    import os

    assert single_instance.RESTART_ENV_VAR not in os.environ


def test_restarted_launch_waits_then_gives_up(name, qapp, monkeypatch):
    monkeypatch.setattr(SingleInstance, "listen", lambda self: False)
    monkeypatch.setattr(single_instance.time, "sleep", lambda _s: None)
    instance = single_instance.acquire(name, restarted=True, takeover_seconds=0)
    assert instance is not None and not instance.is_listening


def test_allow_foreground_is_noop_off_windows(monkeypatch):
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setitem(sys.modules, "ctypes", SimpleNamespace())
    single_instance._allow_foreground(1234)  # must not raise


def test_bring_to_front_restores_minimized_and_keeps_maximized(qapp):
    w = QWidget()
    w.setWindowState(Qt.WindowState.WindowMaximized | Qt.WindowState.WindowMinimized)
    single_instance.bring_to_front(w)
    assert not (w.windowState() & Qt.WindowState.WindowMinimized)
    assert w.windowState() & Qt.WindowState.WindowMaximized
    assert w.isVisible()
    w.close()


def test_bring_to_front_ignores_none():
    single_instance.bring_to_front(None)
