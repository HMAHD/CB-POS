"""Stop the mouse wheel from changing spin boxes and combos the user is only scrolling past (#598).

A guarded field ignores wheel events until it has keyboard focus, so the wheel scrolls the
page instead; once clicked or tabbed into, the wheel changes it as usual.
"""

from PyQt6.QtCore import QEvent, QObject, Qt
from PyQt6.QtWidgets import QAbstractSpinBox, QComboBox, QWidget

GUARDED_TYPES = (QAbstractSpinBox, QComboBox)


class _WheelGuard(QObject):
    """Event filter shared by every guarded field, and the new-child watcher on each root."""

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        """Hand unfocused wheel events to the parent; guard fields that appear under a watched root."""
        etype = event.type()
        if etype == QEvent.Type.Wheel and isinstance(obj, GUARDED_TYPES) and not obj.hasFocus():
            # ignore() + True: the field never sees it and Qt passes it on to the parent (the scroll area).
            event.ignore()
            return True
        # ChildAdded covers fields added (or reparented in) after the guard went on; ChildPolished
        # catches widgets that were still mid-construction when they were added.
        if etype in (QEvent.Type.ChildAdded, QEvent.Type.ChildPolished) and not isinstance(obj, GUARDED_TYPES):
            child = event.child()
            if isinstance(child, QWidget):
                _guard_tree(child)
        return False


_guard: _WheelGuard | None = None


def _shared_guard() -> _WheelGuard:
    global _guard
    if _guard is None:
        _guard = _WheelGuard()
    return _guard


def guard_wheel(widget: QWidget) -> None:
    """Make one spin box/combo take focus only on click or Tab, and ignore the wheel until focused.

    Only the default WheelFocus policy is narrowed, so a field deliberately set to NoFocus stays that way.
    """
    if widget.focusPolicy() == Qt.FocusPolicy.WheelFocus:
        widget.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
    widget.installEventFilter(_shared_guard())


def _guard_tree(root: QWidget) -> None:
    if isinstance(root, GUARDED_TYPES):
        guard_wheel(root)
    for widget in root.findChildren(QAbstractSpinBox) + root.findChildren(QComboBox):
        guard_wheel(widget)


def install_wheel_guard(root: QWidget) -> None:
    """Guard every spin box/combo under `root`, including ones added to it later.

    Call it on a scrollable form or a dialog; it is safe to call more than once.
    """
    _guard_tree(root)
    root.installEventFilter(_shared_guard())
