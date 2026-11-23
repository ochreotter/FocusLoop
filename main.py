"""FocusLoop desktop entry point."""

import sys

from PySide6.QtWidgets import QApplication

from focusloop.app import FocusLoopApp
from focusloop.icons import clock_icon


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("FocusLoop")
    app.setOrganizationName("FocusLoop")
    app.setWindowIcon(clock_icon())
    app.setQuitOnLastWindowClosed(False)
    controller = FocusLoopApp(app)
    if not controller.start():
        return 1
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
