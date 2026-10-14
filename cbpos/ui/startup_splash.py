"""Splash shown while CB POS starts, so users see it is loading (#691)."""

from PyQt6.QtCore import QRect, Qt
from PyQt6.QtGui import QColor, QFont, QPainter, QPixmap
from PyQt6.QtWidgets import QSplashScreen

from cbpos.config import Config
from cbpos.i18n import _t

_SIZE = (360, 320)
_LOGO_SIZE = 220
_BACKGROUND = QColor("#FFFFFF")
_BORDER = QColor("#DEE2E6")
_TEXT = QColor("#495057")


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

    Returns:
        QSplashScreen: The splash, not yet shown.
    """
    splash = QSplashScreen(_splash_pixmap())
    splash.setObjectName("StartupSplash")
    font = QFont(splash.font())
    font.setPointSize(11)
    splash.setFont(font)
    splash.showMessage(
        _t("startup.splash_loading"),
        Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignBottom,
        _TEXT,
    )
    return splash
