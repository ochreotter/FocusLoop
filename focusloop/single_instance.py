"""Single-instance guard and tray-app activation via Qt local IPC.

The lock is per-user and is held for the entire lifetime of the application.
A second launch sends an activation request, then exits without starting a timer.
"""

from __future__ import annotations

import hashlib
import time
from pathlib import Path

from PySide6.QtCore import QObject, QLockFile, QStandardPaths, Signal
from PySide6.QtNetwork import QLocalServer, QLocalSocket


class SingleInstance(QObject):
    """Coordinate one FocusLoop process per Windows user without a port."""

    activate_requested = Signal()

    def __init__(self, lock_directory: Path | None = None) -> None:
        super().__init__()
        directory = lock_directory or Path(
            QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppLocalDataLocation)
        )
        if not str(directory):
            raise RuntimeError("Could not determine the per-user FocusLoop data directory")
        directory.mkdir(parents=True, exist_ok=True)
        lock_path = directory / "FocusLoop-instance.lock"
        # Hash the per-user lock path so separate Windows user profiles can run
        # independent copies without sharing one named-pipe endpoint.
        digest = hashlib.sha256(str(lock_path.resolve()).casefold().encode("utf-8")).hexdigest()
        self.server_name = "focusloop-" + digest[:28]
        self.lock = QLockFile(str(lock_path))
        self.lock.setStaleLockTime(0)  # Never expire a lock held by a living process.
        self._owns_lock = False
        self._server: QLocalServer | None = None
        self._clients: set[QLocalSocket] = set()

    def acquire(self) -> bool:
        """Atomically claim the per-user app slot; no timer starts on failure."""
        if self._owns_lock:
            return True
        self._owns_lock = self.lock.tryLock(0)
        return self._owns_lock

    def listen(self) -> None:
        """Begin receiving activation requests after the controller is ready."""
        if not self._owns_lock:
            raise RuntimeError("Cannot listen without owning the instance lock")
        self._server = QLocalServer(self)
        if not self._server.listen(self.server_name):
            # Only the holder of the exclusive lock may remove a stale endpoint.
            QLocalServer.removeServer(self.server_name)
            if not self._server.listen(self.server_name):
                raise RuntimeError("Could not start the FocusLoop activation channel")
        self._server.newConnection.connect(self._accept_connections)

    def _accept_connections(self) -> None:
        if self._server is None:
            return
        while self._server.hasPendingConnections():
            socket = self._server.nextPendingConnection()
            if socket is None:
                continue
            self._clients.add(socket)
            socket.readyRead.connect(lambda connection=socket: self._read_request(connection))
            socket.disconnected.connect(lambda connection=socket: self._disconnect(connection))
            self._read_request(socket)

    def _read_request(self, socket: QLocalSocket) -> None:
        data = bytes(socket.readAll())
        if data == b"ACTIVATE":
            self.activate_requested.emit()

    def _disconnect(self, socket: QLocalSocket) -> None:
        self._clients.discard(socket)
        socket.deleteLater()

    def notify_existing(self, timeout_seconds: float = 2.0) -> bool:
        """Ask the original instance to show its settings; retry during startup."""
        if self._owns_lock:
            return False
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            client = QLocalSocket()
            client.connectToServer(self.server_name)
            if client.waitForConnected(200):
                queued = client.write(b"ACTIVATE")
                delivered = queued == len(b"ACTIVATE") and (
                    client.waitForBytesWritten(300) or client.bytesToWrite() == 0
                )
                client.disconnectFromServer()
                client.close()
                if delivered:
                    return True
            client.abort()
            time.sleep(0.075)
        return False

    def release(self) -> None:
        """Close IPC before releasing the lock, including on normal app exit."""
        if self._server is not None:
            self._server.close()
            self._server.deleteLater()
            self._server = None
        for client in tuple(self._clients):
            client.abort()
            client.deleteLater()
        self._clients.clear()
        if self._owns_lock:
            QLocalServer.removeServer(self.server_name)
            self.lock.unlock()
            self._owns_lock = False
