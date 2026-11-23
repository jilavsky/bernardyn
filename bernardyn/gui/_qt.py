"""bernardyn.gui._qt — the single Qt import point for Bernardyn.

Every module in the package (GUI, renderers, entry points) and the test suite
imports the Qt names it needs from here, never from ``PySide6`` directly, so
the binding is chosen and pinned in exactly one place.

Two import styles are supported:

* flat names — ``from bernardyn.gui._qt import QWidget, Qt, Signal``
* submodules — ``from bernardyn.gui._qt import QtCore, QtGui, QtWidgets``

PySide6 is the only supported binding (house standard): there is no PyQt6
fallback, and PyQt6 must never be installed next to PySide6 — the two collide
over Qt plugins in one environment.  The PySide6 versions Bernardyn refuses
(6.9.1 draws empty plots, 6.10.x is unsupported) are excluded in
``pyproject.toml`` and reported by ``bernardyn-doctor``.

Importing this module must stay cheap and free of Bernardyn imports, so that
renderers and headless recipes can use it without loading the main window.

Exception: ``bernardyn/renderers/opengl.py`` runs its OpenGL probe as a
script in a separate interpreter and imports PySide6 inside that script text.

To add a Qt name, add it to the matching import below and to ``__all__``.
"""

from __future__ import annotations

import os

from PySide6 import QtCore, QtGui, QtPrintSupport, QtSvg, QtWidgets
from PySide6.QtCore import (
    QBuffer,
    QByteArray,
    QDir,
    QEvent,
    QIODevice,
    QItemSelectionModel,
    QLockFile,
    QMimeData,
    QObject,
    QPointF,
    QRect,
    QRectF,
    QRunnable,
    QSignalBlocker,
    QSize,
    QStandardPaths,
    Qt,
    QThreadPool,
    QTimer,
    QUrl,
    Signal,
)
from PySide6.QtGui import (
    QAction,
    QCloseEvent,
    QColor,
    QDesktopServices,
    QDropEvent,
    QFont,
    QImage,
    QKeySequence,
    QMatrix4x4,
    QPainter,
    QPalette,
    QPixmap,
    QShortcut,
    QUndoCommand,
    QUndoStack,
    QValidator,
)
from PySide6.QtPrintSupport import QPrintDialog, QPrinter
from PySide6.QtSvg import QSvgGenerator
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDockWidget,
    QDoubleSpinBox,
    QFileDialog,
    QFileSystemModel,
    QFontComboBox,
    QFormLayout,
    QGraphicsItem,
    QGraphicsItemGroup,
    QGraphicsRectItem,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QSplitter,
    QStyle,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QToolButton,
    QTreeView,
    QVBoxLayout,
    QWidget,
)

QT_BINDING = "PySide6"

# PyQtGraph picks its own binding and tries PyQt6 *before* PySide6 when
# neither is imported yet.  On a machine with a stray PyQt6 that can put the
# plots on a different binding than the widgets.  Pin it to ours; an explicit
# user setting still wins.  ``bernardyn.renderers`` imports this module before
# any renderer imports pyqtgraph.
os.environ.setdefault("PYQTGRAPH_QT_LIB", QT_BINDING)

__all__ = [
    "QT_BINDING",
    # submodules
    "QtCore",
    "QtGui",
    "QtPrintSupport",
    "QtSvg",
    "QtWidgets",
    # QtCore
    "QBuffer",
    "QByteArray",
    "QDir",
    "QEvent",
    "QIODevice",
    "QItemSelectionModel",
    "QLockFile",
    "QMimeData",
    "QObject",
    "QPointF",
    "QRect",
    "QRectF",
    "QRunnable",
    "QSignalBlocker",
    "QSize",
    "QStandardPaths",
    "QThreadPool",
    "QTimer",
    "QUrl",
    "Qt",
    "Signal",
    # QtGui
    "QAction",
    "QCloseEvent",
    "QColor",
    "QDesktopServices",
    "QDropEvent",
    "QFont",
    "QImage",
    "QKeySequence",
    "QMatrix4x4",
    "QPainter",
    "QPalette",
    "QPixmap",
    "QShortcut",
    "QUndoCommand",
    "QUndoStack",
    "QValidator",
    # QtPrintSupport / QtSvg
    "QPrintDialog",
    "QPrinter",
    "QSvgGenerator",
    # QtWidgets
    "QAbstractItemView",
    "QApplication",
    "QCheckBox",
    "QColorDialog",
    "QComboBox",
    "QDialog",
    "QDialogButtonBox",
    "QDockWidget",
    "QDoubleSpinBox",
    "QFileDialog",
    "QFileSystemModel",
    "QFontComboBox",
    "QFormLayout",
    "QGraphicsItem",
    "QGraphicsItemGroup",
    "QGraphicsRectItem",
    "QGridLayout",
    "QGroupBox",
    "QHBoxLayout",
    "QInputDialog",
    "QLabel",
    "QLineEdit",
    "QListWidget",
    "QListWidgetItem",
    "QMainWindow",
    "QMenu",
    "QMessageBox",
    "QPushButton",
    "QScrollArea",
    "QSizePolicy",
    "QSpinBox",
    "QSplitter",
    "QStyle",
    "QTableWidget",
    "QTableWidgetItem",
    "QTabWidget",
    "QToolButton",
    "QTreeView",
    "QVBoxLayout",
    "QWidget",
]
