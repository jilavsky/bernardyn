"""GUI application entry point."""

from __future__ import annotations

import logging
import sys

from PySide6.QtWidgets import QApplication

from bernardyn.gui.main_window import MainWindow


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("Bernardyn")
    app.setOrganizationName("Bernardyn")
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
