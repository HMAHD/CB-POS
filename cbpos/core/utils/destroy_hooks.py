"""Run cleanup code when a Qt object is destroyed, without risking a segfault.

Do not connect ``obj.destroyed`` to a nested function or a lambda. PyQt
holds a non-method slot through a strong reference that only the sender's
Python wrapper reports to the garbage collector. A view can become cyclic
garbage while its C++ object is still alive, for example between
``deleteLater()`` and the event loop running it. A gc pass then frees the
wrappers of the view's child widgets. sip frees a wrapper without asking
PyQt to drop that wrapper's slots, and gc has already cleared the
nested function: its closure and globals are now NULL. PyQt still holds
the function, so when Qt later destroys the widget and emits
``destroyed``, PyQt calls the cleared function and the interpreter
segfaults.

``call_on_destroyed`` connects a bound method of a small hook object
instead. PyQt holds a bound-method slot through a weak reference to its
instance and a strong reference to the class-level function, which gc
never clears. A module-level ``WeakKeyDictionary`` keeps the hook
reachable for as long as the owner's Python wrapper lives, so gc never
clears the hook or the callback it holds. If the wrapper is collected
first, the hook goes with it and PyQt skips the call.

This module imports no PyQt: ``owner`` only needs a ``destroyed`` signal.
"""

import weakref
from collections.abc import Callable
from typing import Any

# owner wrapper -> hooks connected to its destroyed signal. Weak keys, so a
# hook never keeps its owner alive; the strong values keep every hook (and
# the callback it holds) reachable while the owner's wrapper is alive.
_hooks: "weakref.WeakKeyDictionary[Any, list[_DestroyedHook]]" = weakref.WeakKeyDictionary()


class _DestroyedHook:
    """Bound-method slot that runs one cleanup callback."""

    __slots__ = ("__weakref__", "_args", "_callback")

    def __init__(self, callback: Callable[..., object], args: tuple[object, ...]) -> None:
        """Store the callback and its positional arguments."""
        self._callback = callback
        self._args = args

    def fire(self, *_signal_args: object) -> None:
        """Run the callback. Qt passes the dying object, which is ignored here."""
        self._callback(*self._args)


def call_on_destroyed(owner: Any, callback: Callable[..., object], *args: object) -> None:
    """Call ``callback(*args)`` when ``owner`` emits ``destroyed``.

    Use this instead of ``owner.destroyed.connect(<lambda or nested
    function>)``; the module docstring explains why that form can segfault.

    The hook holds ``callback`` and ``args`` strongly for as long as
    ``owner``'s Python wrapper lives. They must not refer to ``owner``
    strongly (a bound method of ``owner`` does), or the wrapper is never
    freed; use a weakref, as ``register_language_callback`` does.

    Args:
        owner: A QObject (anything with a ``destroyed`` signal).
        callback: Called once when ``owner`` is destroyed.
        *args: Positional arguments passed to ``callback``.
    """
    hook = _DestroyedHook(callback, args)
    _hooks.setdefault(owner, []).append(hook)
    owner.destroyed.connect(hook.fire)
