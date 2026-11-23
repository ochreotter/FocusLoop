"""FocusLoop desktop entry point."""

import sys

from PySide6.QtWidgets import QApplication

from focusloop.app import FocusLoopApp


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("FocusLoop")
    app.setOrganizationName("FocusLoop")
    app.setQuitOnLastWindowClosed(False)
    controller = FocusLoopApp(app)
    if not controller.start():
        return 1
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
