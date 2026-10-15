"""Shared styling helpers for Qt widgets."""

from __future__ import annotations

from PyQt6.QtWidgets import QWidget


def refresh_style(widget: QWidget) -> None:
    """Force a QSS style recalculation by unpolishing and polishing the widget."""
    style = widget.style()
    if style is not None:
        style.unpolish(widget)
        style.polish(widget)


def set_status_class(widget: QWidget, css_class: str, text: str | None = None) -> None:
    """Set a QSS class property and force a style refresh, optionally updating widget text."""
    widget.setProperty("class", css_class)
    if text is not None and hasattr(widget, "setText"):
        widget.setText(text)
    refresh_style(widget)
