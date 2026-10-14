"""Keep one running CB POS per user and data folder (#691).

The first instance listens on a ``QLocalServer`` (a named pipe on Windows, a
socket file elsewhere). A later launch connects, asks it to come to the front
and exits before doing any heavy startup work. Several copies on one SQLite
database would otherwise race each other's writes.

Protocol: on connect the server sends its PID (so the new process can let
it take the foreground on Windows), the client sends ``activate``.

The Inno Setup mutex ``CBPOSAppMutex`` in ``main.py`` is separate and stays.
"""

import getpass
import hashlib
import logging
import os
import sys
import time
from pathlib import Path

from PyQt6.QtCore import QObject, Qt, pyqtSignal
from PyQt6.QtNetwork import QAbstractSocket, QLocalServer, QLocalSocket
from PyQt6.QtWidgets import QWidget

from cbpos.config import Config

logger = logging.getLogger(__name__)

ACTIVATE_MESSAGE = b"activate"

# Set by app_restart in the old process; the relaunched process must take
# over instead of handing off to the instance that is shutting down.
RESTART_ENV_VAR = "CBPOS_RESTARTED"

_active: "SingleInstance | None" = None


def server_name(data_dir: Path | str | None = None, user: str | None = None) -> str:
    """Build the per-user, per-data-folder server name.

    Args:
        data_dir: Data folder the instance owns (defaults to ``Config.DATA_DIR``),
            so a dev checkout never blocks the installed app.
        user: Login name (defaults to the current user).

    Returns:
        str: A short name that is safe for both named pipes and socket files.
    """
    if user is None:
        try:
            user = getpass.getuser()
        except Exception:
            user = os.environ.get("USERNAME") or os.environ.get("USER") or "user"
    folder = str(Path(data_dir if data_dir is not None else Config.DATA_DIR).resolve())
    if sys.platform == "win32":
        folder = folder.lower()
    digest = hashlib.sha256(f"{user}|{folder}".encode()).hexdigest()[:16]
    return f"cbpos-{digest}"


def _allow_foreground(pid: int) -> None:
    """Let the running instance steal focus from us (Windows foreground lock)."""
    if sys.platform != "win32" or pid <= 0:
        return
    try:
        import ctypes

        ctypes.windll.user32.AllowSetForegroundWindow(pid)
    except (AttributeError, OSError):
        pass


class SingleInstance(QObject):
    """Owns the local server for the running instance.

    Signals:
        activation_requested: Another launch asked this instance to come to the front.
    """

    activation_requested = pyqtSignal()

    def __init__(self, name: str, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.name = name
        self._server: QLocalServer | None = None
        self._buffers: dict[int, bytes] = {}

    # -- client side -------------------------------------------------------

    def notify_running_instance(self, timeout_ms: int = 1000) -> bool:
        """Ask an already running instance to activate.

        Args:
            timeout_ms: Per-step wait for connect / reply / write.

        Returns:
            bool: True if another instance is running and got the message.
        """
        sock = QLocalSocket()
        sock.connectToServer(self.name)
        if not sock.waitForConnected(timeout_ms):
            return False
        # The running instance may be busy (migrations, building the main
        # window) and not answer yet -- the request still waits in the pipe.
        if sock.waitForReadyRead(min(timeout_ms, 500)):
            try:
                _allow_foreground(int(bytes(sock.readAll()).strip() or b"0"))
            except ValueError:
                pass
        sock.write(ACTIVATE_MESSAGE + b"\n")
        sock.flush()
        sock.waitForBytesWritten(timeout_ms)
        # Give the server a moment to read before our end of the pipe goes away.
        if sock.state() != QLocalSocket.LocalSocketState.UnconnectedState:
            sock.waitForDisconnected(timeout_ms)
        sock.abort()
        return True

    # -- server side -------------------------------------------------------

    def listen(self) -> bool:
        """Start listening; clears a stale socket left by a crashed instance.

        Returns:
            bool: True if this process now owns the name.
        """
        server = QLocalServer(self)
        server.setSocketOptions(QLocalServer.SocketOption.UserAccessOption)
        ok = server.listen(self.name)
        if not ok and server.serverError() == QAbstractSocket.SocketError.AddressInUseError:
            QLocalServer.removeServer(self.name)
            ok = server.listen(self.name)
        if not ok:
            logger.warning("Single-instance server could not listen on %s: %s", self.name, server.errorString())
            server.deleteLater()
            return False
        server.newConnection.connect(self._on_new_connection)
        self._server = server
        return True

    @property
    def is_listening(self) -> bool:
        """True while this process owns the name."""
        return self._server is not None and self._server.isListening()

    def close(self) -> None:
        """Stop listening so a relaunched process can take the name."""
        if self._server is not None:
            self._server.close()
            self._server.deleteLater()
            self._server = None

    def _on_new_connection(self) -> None:
        server = self._server
        if server is None:
            return
        while server.hasPendingConnections():
            sock = server.nextPendingConnection()
            if sock is None:
                break
            sock.readyRead.connect(lambda s=sock: self._on_ready_read(s))
            sock.disconnected.connect(sock.deleteLater)
            sock.write(f"{os.getpid()}\n".encode())
            sock.flush()
            if sock.bytesAvailable():
                self._on_ready_read(sock)

    def _on_ready_read(self, sock: QLocalSocket) -> None:
        key = id(sock)
        data = self._buffers.get(key, b"") + bytes(sock.readAll())
        if ACTIVATE_MESSAGE in data:
            self._buffers.pop(key, None)
            self.activation_requested.emit()
            sock.disconnectFromServer()
        else:
            self._buffers[key] = data[-64:]


def acquire(
    name: str | None = None, restarted: bool | None = None, takeover_seconds: float = 5.0
) -> SingleInstance | None:
    """Become the single running instance, or hand off to the one already running.

    Args:
        name: Server name (defaults to :func:`server_name`).
        restarted: True when launched by our own restart (#673). Then the old
            instance is on its way out, so never hand off to it; keep trying to
            listen for ``takeover_seconds``. Defaults to reading and clearing
            ``RESTART_ENV_VAR``.
        takeover_seconds: How long a restarted launch waits for the name.

    Returns:
        SingleInstance | None: The listening instance, or None if another
        instance is running and was asked to activate (caller should exit).
    """
    global _active
    if restarted is None:
        restarted = os.environ.pop(RESTART_ENV_VAR, None) == "1"
    instance = SingleInstance(name or server_name())

    if restarted:
        deadline = time.monotonic() + takeover_seconds
        while not instance.listen():
            if time.monotonic() >= deadline:
                logger.warning("Restarted CB POS could not claim the single-instance name; continuing without it")
                break
            time.sleep(0.2)
        _active = instance
        return instance

    if instance.notify_running_instance():
        logger.info("CB POS is already running; asked it to come to the front")
        return None
    if not instance.listen():
        # Rather run than refuse to start; the user can still use the app.
        logger.warning("Continuing without single-instance protection")
    _active = instance
    return instance


def release() -> None:
    """Close the active instance's server (before a restart relaunches us)."""
    global _active
    if _active is not None:
        _active.close()
        _active = None


def bring_to_front(widget: QWidget | None) -> None:
    """Restore, raise and activate a window without dropping its maximized state.

    Args:
        widget: The window to show; ignored if None.
    """
    if widget is None:
        return
    state = widget.windowState()
    if state & Qt.WindowState.WindowMinimized:
        widget.setWindowState((state & ~Qt.WindowState.WindowMinimized) | Qt.WindowState.WindowActive)
    widget.show()
    widget.raise_()
    widget.activateWindow()
