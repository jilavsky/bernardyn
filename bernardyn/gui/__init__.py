"""GUI layer for Bernardyn.

``MainWindow`` is imported lazily: the Qt shim ``bernardyn.gui._qt`` and the
vendored ``raised_buttons`` live in this package, and importing them (from the
renderers or headless recipes) must not load the whole main window.
"""

from __future__ import annotations

__all__ = ["MainWindow"]


def __getattr__(name: str):
    if name == "MainWindow":
        from bernardyn.gui.main_window import MainWindow

        return MainWindow
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
