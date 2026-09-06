"""GUI application entry point."""

from __future__ import annotations

import logging
import os
import sys

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from bernardyn.gui.main_window import MainWindow


def main() -> int:
    # BERNARDYN_LOG_LEVEL=DEBUG turns on the per-annotation placement trace
    # and the renderer's coordinate diagnostics.
    level = os.environ.get("BERNARDYN_LOG_LEVEL", "INFO").upper()
    logging.basicConfig(
        level=getattr(logging, level, logging.INFO),
        format="%(levelname)s %(name)s: %(message)s",
    )
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("Bernardyn")
    app.setOrganizationName("Bernardyn")
    window = MainWindow()
    window.show()
    # Run after the window is visible so a stored dock layout can be restored
    # along with the saved workspace.
    QTimer.singleShot(0, window.restore_last_workspace)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
