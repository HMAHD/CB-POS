"""Window/taskbar icon (#692): the app icon must load and be applied to the
QApplication so every window and dialog inherits it; the Windows
AppUserModelID call must be a harmless no-op elsewhere.
"""

import sys
from types import SimpleNamespace

from PyQt6.QtGui import QIcon

from cbpos.config import Config
from cbpos.infrastructure import app_identity


def test_icon_file_is_inside_bundled_assets():
    path = app_identity.app_icon_path()
    assert path.is_file()
    # cbpos.spec bundles the whole cbpos/assets tree, so the frozen build has it too.
    assert path.relative_to(Config.BASE_DIR).parts[:2] == ("cbpos", "assets")


def test_spec_bundles_assets_directory():
    spec = (Config.BASE_DIR / "cbpos.spec").read_text(encoding="utf-8")
    assert "('cbpos/assets', 'cbpos/assets')" in spec


def test_apply_app_icon_sets_non_null_window_icon(qapp):
    previous = qapp.windowIcon()
    try:
        qapp.setWindowIcon(QIcon())
        icon = app_identity.apply_app_icon(qapp)
        assert not icon.isNull()
        assert not qapp.windowIcon().isNull()
        assert qapp.windowIcon().availableSizes()
    finally:
        qapp.setWindowIcon(previous)


def test_falls_back_to_png_when_ico_unreadable(monkeypatch, tmp_path):
    monkeypatch.setattr(app_identity, "app_icon_path", lambda: tmp_path / "missing.ico")
    assert not app_identity.load_app_icon().isNull()


def test_app_user_model_id_noop_off_windows(monkeypatch):
    monkeypatch.setattr(sys, "platform", "darwin")
    assert app_identity.set_windows_app_user_model_id() is False


def test_app_user_model_id_set_on_windows(monkeypatch):
    calls: list[str] = []
    fake_ctypes = SimpleNamespace(
        windll=SimpleNamespace(shell32=SimpleNamespace(SetCurrentProcessExplicitAppUserModelID=calls.append))
    )
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setitem(sys.modules, "ctypes", fake_ctypes)
    assert app_identity.set_windows_app_user_model_id() is True
    assert calls == ["CeyByte.CBPOS"]


def test_app_user_model_id_failure_is_swallowed(monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setitem(sys.modules, "ctypes", SimpleNamespace())  # no windll
    assert app_identity.set_windows_app_user_model_id() is False
