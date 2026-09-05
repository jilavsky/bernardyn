"""GUI application entry point."""

from __future__ import annotations

import logging
import os
import sys

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
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
