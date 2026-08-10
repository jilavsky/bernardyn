"""Main entry point for Bernardyn."""

import sys
from PySide6.QtWidgets import QApplication

from bernardyn.gui.main_window import MainWindow


def main():
    """Run the Bernardyn application."""
    app = QApplication(sys.argv)
    app.setApplicationName("Bernardyn")
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
