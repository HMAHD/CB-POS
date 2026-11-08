"""Modal Dialog Dimming Overlay and Table Alternating Row Colors Enforcement.

Provides:
- ModalDimmer: A non-intrusive backdrop overlay placed over a parent window or dialog
  when a modal dialog opens in front of it.
- ModalDimmerManager: An application-level event filter that automatically shows the
  dimmer behind any modal QDialog and ensures dialog tables/trees use alternating row colors.
- install_modal_dimmer_filter / uninstall_modal_dimmer_filter: Helper functions to activate/deactivate.
"""

from __future__ import annotations

import logging
from typing import Any

from PyQt6 import sip
from PyQt6.QtCore import QEvent, QObject, Qt
from PyQt6.QtGui import QColor, QPainter
from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QMainWindow,
    QTableView,
    QTableWidget,
    QTreeView,
    QTreeWidget,
    QWidget,
)

from cbpos.core.utils.destroy_hooks import call_on_destroyed

logger = logging.getLogger(__name__)


class ModalDimmer(QWidget):
    """Semi-transparent scrim widget that covers a parent window behind an active modal dialog.

    Features:

    - Automatically resizes with the parent window via an event filter.
    - Uses theme-aware backdrop colors (dark mode: subtle deep veil; light mode: clean slate veil).
    - Uses WA_TransparentForMouseEvents so mouse clicks are not swallowed and Qt's modal loop
      can handle window activation natively.
    """

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setObjectName("ModalDimmer")
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setGeometry(parent.rect())
        parent.installEventFilter(self)

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        """Keep dimmer geometry matched to the parent window geometry."""
        if obj == self.parent() and event.type() in (QEvent.Type.Resize, QEvent.Type.Move):
            parent = self.parent()
            if isinstance(parent, QWidget):
                self.setGeometry(parent.rect())
        return super().eventFilter(obj, event)

    def paintEvent(self, _event):
        """Paint a semi-transparent scrim with theme-aware shading."""
        painter = QPainter(self)
        try:
            from cbpos.core.services.theme_service import ThemeService

            theme = (ThemeService.current_theme or "Dark").lower()
        except Exception:
            theme = "dark"

        # Dark theme: deep black veil with 45% opacity
        # Light theme: dark slate veil with 32% opacity
        color = QColor(0, 0, 0, 115) if theme == "dark" else QColor(15, 23, 42, 80)
        painter.fillRect(self.rect(), color)


class _IdKeyedDict(dict):
    """Dictionary that transparently normalizes QWidget/QObject keys to id(widget).

    Prevents keeping strong Python references to widgets in process-wide manager dicts (#918).
    """

    def __getitem__(self, key: Any) -> Any:
        return super().__getitem__(id(key) if not isinstance(key, int) else key)

    def __setitem__(self, key: Any, value: Any) -> None:
        super().__setitem__(id(key) if not isinstance(key, int) else key, value)

    def __contains__(self, key: Any) -> bool:
        return super().__contains__(id(key) if not isinstance(key, int) else key)

    def get(self, key: Any, default: Any = None) -> Any:
        return super().get(id(key) if not isinstance(key, int) else key, default)

    def pop(self, key: Any, *args: Any) -> Any:
        return super().pop(id(key) if not isinstance(key, int) else key, *args)


class ModalDimmerManager(QObject):
    """Application-wide event filter managing modal dimmers and dialog alternating row colors."""

    _instance: ModalDimmerManager | None = None

    def __init__(self):
        super().__init__()
        self._dimmers: _IdKeyedDict = _IdKeyedDict()
        self._active_modals: _IdKeyedDict = _IdKeyedDict()
        self._modal_to_target: dict[int, int] = {}
        self._connected_targets: set[int] = set()
        self._connected_modals: set[int] = set()

    @classmethod
    def instance(cls) -> ModalDimmerManager:
        """Returns the process-wide singleton instance of ModalDimmerManager."""
        if cls._instance is None:
            cls._instance = ModalDimmerManager()
        return cls._instance

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        """Intercept Show and Hide events on modal QDialogs."""
        if isinstance(obj, QDialog):
            if event.type() == QEvent.Type.Show:
                # Modality can be WindowModal, ApplicationModal, or modal property set
                if obj.isModal() or obj.windowModality() != Qt.WindowModality.NonModal:
                    self._on_modal_shown(obj)
            elif event.type() == QEvent.Type.Hide:
                self._on_modal_hidden(obj)

        return super().eventFilter(obj, event)

    def _get_target_window(self, dialog: QDialog) -> QWidget | None:
        parent = dialog.parentWidget()
        if parent:
            target = parent.window()
        else:
            target = QApplication.activeWindow()

        if target == dialog or target is None:
            # Fall back to finding a visible QMainWindow (such as the main application window)
            for top in QApplication.topLevelWidgets():
                if isinstance(top, QMainWindow) and top.isVisible():
                    return top
            return None

        return target

    def _on_modal_shown(self, dialog: QDialog):
        # 1. Ensure all tables/trees in the modal dialog have alternating row colors enabled
        self._enable_alternating_colors(dialog)

        # 2. Dim the window behind the modal dialog
        target = self._get_target_window(dialog)
        if not target or target == dialog or not target.isVisible():
            return

        target_id = id(target)
        dialog_id = id(dialog)

        if target_id not in self._active_modals:
            self._active_modals[target_id] = set()

        if target_id not in self._connected_targets:
            self._connected_targets.add(target_id)
            try:
                call_on_destroyed(target, self._on_target_destroyed_by_id, target_id)
            except Exception:
                pass

        self._active_modals[target_id].add(dialog_id)
        self._modal_to_target[dialog_id] = target_id

        if dialog_id not in self._connected_modals:
            self._connected_modals.add(dialog_id)
            try:
                call_on_destroyed(dialog, self._on_modal_hidden_by_id, dialog_id)
            except Exception:
                pass

        dimmer = self._dimmers.get(target_id)
        if not dimmer or sip.isdeleted(dimmer) or dimmer.parent() != target:
            dimmer = ModalDimmer(target)
            self._dimmers[target_id] = dimmer

        dimmer.setGeometry(target.rect())
        dimmer.show()
        dimmer.raise_()

    def _on_modal_hidden(self, dialog: QDialog):
        self._on_modal_hidden_by_id(id(dialog))

    def _on_modal_hidden_by_id(self, dialog_id: int):
        self._connected_modals.discard(dialog_id)
        target_id = self._modal_to_target.pop(dialog_id, None)
        if target_id is not None:
            dialogs = self._active_modals.get(target_id)
            if dialogs:
                dialogs.discard(dialog_id)
                if not dialogs:
                    dimmer = self._dimmers.get(target_id)
                    if dimmer and not sip.isdeleted(dimmer):
                        dimmer.hide()
                    self._active_modals.pop(target_id, None)
        else:
            for t_id, dialogs in list(self._active_modals.items()):
                if dialog_id in dialogs:
                    dialogs.discard(dialog_id)
                    if not dialogs:
                        dimmer = self._dimmers.get(t_id)
                        if dimmer and not sip.isdeleted(dimmer):
                            dimmer.hide()
                        self._active_modals.pop(t_id, None)

    def _on_target_destroyed(self, target: QWidget):
        self._on_target_destroyed_by_id(id(target))

    def _on_target_destroyed_by_id(self, target_id: int):
        self._connected_targets.discard(target_id)
        dimmer = self._dimmers.pop(target_id, None)
        if dimmer and not sip.isdeleted(dimmer):
            dimmer.hide()
        dialog_ids = self._active_modals.pop(target_id, set())
        for d_id in dialog_ids:
            self._modal_to_target.pop(d_id, None)

    @staticmethod
    def _enable_alternating_colors(widget: QWidget):
        """Enables alternating row colors on all tables and trees inside the widget."""
        for view in widget.findChildren((QTableWidget, QTableView, QTreeWidget, QTreeView)):
            if not view.alternatingRowColors():
                view.setAlternatingRowColors(True)


def install_modal_dimmer_filter(app: QApplication | None = None) -> ModalDimmerManager:
    """Installs the ModalDimmerManager event filter on the QApplication instance."""
    qapp = app or QApplication.instance()
    if qapp is None:
        return ModalDimmerManager.instance()

    mgr = ModalDimmerManager.instance()
    qapp.removeEventFilter(mgr)  # Prevent duplicate registration
    qapp.installEventFilter(mgr)
    return mgr


def uninstall_modal_dimmer_filter(app: QApplication | None = None):
    """Uninstalls the ModalDimmerManager event filter."""
    qapp = app or QApplication.instance()
    if qapp is not None and ModalDimmerManager._instance is not None:
        qapp.removeEventFilter(ModalDimmerManager._instance)
