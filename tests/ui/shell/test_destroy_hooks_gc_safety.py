"""destroyed-signal cleanup must survive a gc pass that runs before deleteLater().

The old pattern, ``self.destroyed.connect(<nested _unregister function>)``,
crashed the full unit suite with a segfault: a view whose wrapper sat in a
reference cycle was deleteLater()'d, gc collected its wrappers while the
C++ widgets were still alive and cleared the nested function, and the
deferred delete then emitted ``destroyed`` into that cleared function.
``call_on_destroyed`` and ``register_language_callback(..., owner=)``
avoid this; see cbpos/core/utils/destroy_hooks.py.
"""

import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest
from PyQt6.QtCore import QCoreApplication, QEvent, QObject
from PyQt6.QtWidgets import QWidget

from cbpos.core.utils.destroy_hooks import call_on_destroyed
from cbpos.i18n import _service, register_language_callback

pytestmark = pytest.mark.usefixtures("qapp")

REPO_ROOT = Path(__file__).resolve().parents[3]

# A child widget inside a view that is cyclic garbage when deleteLater()
# runs: the exact shape that used to segfault. Run in a subprocess so a
# regression fails this test instead of killing the whole suite.
_SCENARIO = textwrap.dedent(
    """
    import gc
    from PyQt6.QtCore import QCoreApplication, QEvent
    from PyQt6.QtWidgets import QApplication, QWidget

    from cbpos.core.utils.destroy_hooks import call_on_destroyed
    from cbpos.i18n import register_language_callback

    app = QApplication([])


    class Child(QWidget):
        def __init__(self, parent):
            super().__init__(parent)
            register_language_callback(self.retranslate_ui, owner=self)
            call_on_destroyed(self, print, "child destroyed")

        def retranslate_ui(self):
            pass


    class View(QWidget):
        def __init__(self):
            super().__init__()
            self.child = Child(QWidget(self))
            self.cycle = self


    View().deleteLater()
    gc.collect()  # collects the view's wrappers while the C++ widgets live on
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete.value)
    print("survived")
    """
)


def _flush_deferred_deletes() -> None:
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete.value)


def test_gc_before_deferred_delete_does_not_crash():
    env = {**os.environ, "QT_QPA_PLATFORM": "offscreen"}
    result = subprocess.run(
        [sys.executable, "-c", _SCENARIO],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, f"exit {result.returncode}\n{result.stderr[-2000:]}"
    assert "survived" in result.stdout


def test_callback_runs_with_args_when_owner_is_destroyed():
    calls = []
    owner = QObject()
    call_on_destroyed(owner, calls.append, "gone")
    owner.deleteLater()
    _flush_deferred_deletes()
    assert calls == ["gone"]


def test_owner_language_callback_is_unregistered_on_destroy():
    class View(QWidget):
        def retranslate_ui(self) -> None:
            pass

    view = View()
    register_language_callback(view.retranslate_ui, owner=view)

    def registered() -> bool:
        return any(ref() == view.retranslate_ui for ref in _service._change_callbacks)

    assert registered()
    view.deleteLater()
    _flush_deferred_deletes()
    assert not registered()


def test_hook_does_not_keep_owner_alive():
    destroyed = []
    owner = QObject()
    owner.destroyed.connect(lambda: destroyed.append(True))
    call_on_destroyed(owner, lambda: None)
    del owner  # Python-owned with no parent: refcounting alone must free it
    assert destroyed == [True]
