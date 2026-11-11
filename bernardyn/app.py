"""GUI application entry point."""

from __future__ import annotations

import logging
import os
import sys
import threading
from logging.handlers import RotatingFileHandler
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QApplication

from bernardyn import __version__
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


LOG_DIRECTORY = Path.home() / ".bernardyn" / "logs"
LOG_FILE_NAME = "bernardyn.log"
log = logging.getLogger("bernardyn")


def configure_logging(level: str = "INFO", directory: Path | None = None) -> Path | None:
    """Log to stderr (when there is one) and to a rotating file.

    ``bernardyn`` is a GUI script: on Windows it has no console, so without
    the file an error that only reaches the log would vanish.  Returns the
    log file path, or None when it cannot be created (read-only home).
    """
    root = logging.getLogger()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    if sys.stderr is not None and not any(
        isinstance(handler, logging.StreamHandler)
        and not isinstance(handler, logging.FileHandler)
        for handler in root.handlers
    ):
        stream = logging.StreamHandler()
        stream.setFormatter(logging.Formatter("%(levelname)s %(name)s: %(message)s"))
        root.addHandler(stream)
    folder = directory or LOG_DIRECTORY
    try:
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / LOG_FILE_NAME
        if not any(
            isinstance(handler, RotatingFileHandler) and Path(handler.baseFilename) == path
            for handler in root.handlers
        ):
            handler = RotatingFileHandler(
                path, maxBytes=1_000_000, backupCount=3, encoding="utf-8"
            )
            handler.setFormatter(formatter)
            root.addHandler(handler)
        return path
    except OSError:
        log.warning("could not create the log file in %s", folder, exc_info=True)
        return None


def install_exception_hooks(log_path: Path | None) -> None:
    """Log every uncaught exception and show it, instead of losing it.

    PySide routes exceptions raised in slots through ``sys.excepthook``;
    without a hook they are printed to a console a Windows GUI process does
    not have.  Worker-thread exceptions are logged only (no dialogs off the
    GUI thread).
    """
    showing = False

    def report(kind, value, traceback) -> None:
        nonlocal showing
        if issubclass(kind, KeyboardInterrupt):
            sys.__excepthook__(kind, value, traceback)
            return
        log.critical("Uncaught exception", exc_info=(kind, value, traceback))
        app = QApplication.instance()
        if app is None or showing or threading.current_thread() is not threading.main_thread():
            return
        showing = True
        try:
            from PySide6.QtWidgets import QMessageBox

            details = f"\n\nDetails were written to {log_path}." if log_path else ""
            QMessageBox.critical(
                None,
                "Bernardyn error",
                f"An unexpected error occurred:\n\n{kind.__name__}: {value}{details}\n\n"
                "Your work has not been saved automatically; consider saving under a new name.",
            )
        finally:
            showing = False

    def report_thread(arguments: threading.ExceptHookArgs) -> None:
        log.critical(
            "Uncaught exception in thread %s",
            getattr(arguments.thread, "name", "?"),
            exc_info=(arguments.exc_type, arguments.exc_value, arguments.exc_traceback),
        )

    sys.excepthook = report
    threading.excepthook = report_thread


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) == 1 and args[0] in {"--version", "-version", "--v", "-V"}:
        print(f"Bernardyn {__version__}")
        return 0
    # BERNARDYN_LOG_LEVEL=DEBUG turns on the per-annotation placement trace
    # and the renderer's coordinate diagnostics.
    level = os.environ.get("BERNARDYN_LOG_LEVEL", "INFO").upper()
    log_path = configure_logging(level)
    install_exception_hooks(log_path)
    log.info("Bernardyn %s starting", __version__)
    app = QApplication.instance() or QApplication([sys.argv[0], *args])
    app.setApplicationName("Bernardyn")
    app.setApplicationVersion(__version__)
    app.setOrganizationName("Bernardyn")
    windows = WorkspaceWindowManager()
    window = windows.new_window()
    # Run after the window is visible so a stored dock layout can be restored
    # along with the saved workspace.
    QTimer.singleShot(0, window.restore_last_workspace)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
