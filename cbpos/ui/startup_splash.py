"""Splash shown while CB POS starts, so users see it is loading (#691).

Its line changes as startup moves through real steps (#722):
``set_startup_status(key)`` is called at each step boundary in main().
"""

import weakref

from PyQt6.QtCore import QRect, Qt
from PyQt6.QtGui import QColor, QFont, QPainter, QPixmap
from PyQt6.QtWidgets import QApplication, QSplashScreen

from cbpos.config import Config
from cbpos.i18n import _t

_SIZE = (460, 320)  # wide enough for every startup step on one line (#722)
_LOGO_SIZE = 220
_BACKGROUND = QColor("#FFFFFF")
_BORDER = QColor("#DEE2E6")
_TEXT = QColor("#495057")
_MESSAGE_ALIGN = Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignBottom

# The splash set_startup_status() writes to. A weak reference, so dropping
# main()'s splash still frees it.
_active: "weakref.ref[QSplashScreen] | None" = None


def _splash_pixmap() -> QPixmap:
    """Draw the logo card the message is shown on."""
    width, height = _SIZE
    pixmap = QPixmap(width, height)
    pixmap.fill(_BACKGROUND)

    logo = QPixmap(str(Config.BASE_DIR / "cbpos" / "assets" / "ico" / "cbpos.png"))
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    if not logo.isNull():
        logo = logo.scaled(
            _LOGO_SIZE,
            _LOGO_SIZE,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        painter.drawPixmap((width - logo.width()) // 2, 24, logo)
    painter.setPen(_BORDER)
    painter.drawRect(QRect(0, 0, width - 1, height - 1))
    painter.end()
    return pixmap


def create_startup_splash() -> QSplashScreen:
    """Build the startup splash with the translated "Starting CB POS..." line.

    Call after the language is set. The caller shows it, keeps a reference,
    and calls ``finish(window)`` / ``close()`` once a real window appears.
    It becomes the splash ``set_startup_status()`` updates.

    Returns:
        QSplashScreen: The splash, not yet shown.
    """
    splash = QSplashScreen(_splash_pixmap())
    splash.setObjectName("StartupSplash")
    font = QFont(splash.font())
    font.setPointSize(11)
    splash.setFont(font)
    splash.showMessage(_t("startup.splash_loading"), _MESSAGE_ALIGN, _TEXT)

    global _active
    _active = weakref.ref(splash)
    return splash


def set_startup_status(key: str) -> None:
    """Show the step that is starting now on the splash, and paint it at once.

    Startup runs on the UI thread, so the text is painted here, between
    steps. Call it only right before a step that really runs -- never for
    one that is skipped. Does nothing once the splash is closed (e.g. while
    the setup wizard is open).

    Args:
        key: An i18n key under ``startup.*``.
    """
    splash = _active() if _active is not None else None
    if splash is None or not splash.isVisible():
        return
    splash.showMessage(_t(key), _MESSAGE_ALIGN, _TEXT)
    QApplication.processEvents()
