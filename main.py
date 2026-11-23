"""FocusLoop desktop entry point."""

import sys

from PySide6.QtWidgets import QApplication

from focusloop.app import FocusLoopApp
from focusloop.icons import clock_icon
from focusloop.single_instance import SingleInstance


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("FocusLoop")
    app.setOrganizationName("FocusLoop")
    app.setWindowIcon(clock_icon())
    app.setQuitOnLastWindowClosed(False)

    instance = SingleInstance()
    if not instance.acquire():
        # Do not create another tray icon or timer. Activate the existing UI.
        instance.notify_existing()
        return 0

    try:
        controller = FocusLoopApp(app)
        instance.activate_requested.connect(controller.show_settings)
        if not controller.start():
            return 1
        instance.listen()
        return app.exec()
    finally:
        # The Windows updater waits for this process to exit before replacing
        # FocusLoop.exe; release IPC resources and the lock on shutdown.
        instance.release()


if __name__ == "__main__":
    raise SystemExit(main())
