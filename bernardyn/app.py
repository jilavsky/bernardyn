"""GUI application entry point."""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QApplication

from bernardyn.gui.main_window import MainWindow


class WorkspaceWindowManager:
    """Own every top-level window in this process and route workspace opens."""

    def __init__(self) -> None:
        self.windows: list[MainWindow] = []

    def _make_window(self) -> MainWindow:
        window = MainWindow()
        window.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        window.newWindowRequested.connect(self.new_window)
        window.openWorkspaceRequested.connect(self.open_workspace)
        window.destroyed.connect(lambda *_: self._forget_window(window))
        self.windows.append(window)
        return window

    def _forget_window(self, window: MainWindow) -> None:
        if window in self.windows:
            self.windows.remove(window)

    @staticmethod
    def _activate(window: MainWindow) -> None:
        window.show()
        window.raise_()
        window.activateWindow()

    def new_window(self) -> MainWindow:
        window = self._make_window()
        window.show()
        return window

    def open_workspace(self, path: str | Path) -> MainWindow | None:
        target = Path(path).expanduser().resolve()
        for window in self.windows:
            if window.workspace_path == target:
                self._activate(window)
                return window
        window = self._make_window()
        if not window.open_workspace(target):
            window.deleteLater()
            return None
        self._activate(window)
        return window


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
    windows = WorkspaceWindowManager()
    window = windows.new_window()
    # Run after the window is visible so a stored dock layout can be restored
    # along with the saved workspace.
    QTimer.singleShot(0, window.restore_last_workspace)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
