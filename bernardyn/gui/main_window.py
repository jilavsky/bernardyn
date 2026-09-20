"""Controller-driven Bernardyn desktop workbench."""

from __future__ import annotations

import base64
import json
import logging
from dataclasses import replace
from pathlib import Path

from PySide6.QtCore import (
    QEvent,
    QLockFile,
    QObject,
    QRunnable,
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
    QDesktopServices,
    QKeySequence,
    QUndoCommand,
    QUndoStack,
)
from PySide6.QtPrintSupport import QPrintDialog, QPrinter
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDockWidget,
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from bernardyn.core.controller import PALETTE, ApplicationController
from bernardyn.core.models import AxisSpec, GraphDocument
from bernardyn.gui.dataset_filters import DATASET_FILTERS, matches_dataset_filter
from bernardyn.gui.dialogs import (
    DataFileSelectorDialog,
    GraphSelectionDialog,
    HDFMappingDialog,
    LocationDialog,
    SeriesTransformParameterDialog,
)
from bernardyn.gui.graph_page import GraphPage, OutputPreviewDialog, PreviewPage
from bernardyn.gui.inspector import InspectorWidget
from bernardyn.io.container import ensure_package_suffix, load_package
from bernardyn.io.igor import export_datasets_to_h5xp
from bernardyn.io.results import (
    available_curve_kinds,
    discover_results,
    load_result_bundle,
    load_result_curve,
)
from bernardyn.renderers import builtin_renderers
from bernardyn.state import UserState
from bernardyn.template.graph_templates import apply_template, load_template, save_template

log = logging.getLogger(__name__)

DOCUMENTATION_DIRECTORY = Path(__file__).resolve().parents[2] / "docs"
DOCUMENTATION_URL = "https://github.com/jilavsky/Bernardyn/tree/main/docs"
LAST_WORKSPACE_PATH_KEY = "last_workspace_path"
RECENT_WORKSPACES_KEY = "recent_workspace_paths"
RECENT_WORKSPACES_LIMIT = 10


def _documentation_url() -> QUrl:
    """Open local docs for an editable checkout, GitHub docs for a wheel."""
    if DOCUMENTATION_DIRECTORY.is_dir():
        return QUrl.fromLocalFile(str(DOCUMENTATION_DIRECTORY))
    return QUrl(DOCUMENTATION_URL)


def _metadata_number(value, key: str) -> float | None:
    if not isinstance(value, dict):
        return None
    for name, item in value.items():
        if str(name).lower() == key.lower():
            try:
                return float(item)
            except (TypeError, ValueError):
                pass
    for item in value.values():
        found = _metadata_number(item, key)
        if found is not None:
            return found
    return None


def _axis_label(label: str, unit: str) -> str:
    return f"{label} [{unit}]" if unit else label


class WorkerSignals(QObject):
    loaded = Signal(object, object)
    failed = Signal(str)
    finished = Signal(object)


class SourceLoadWorker(QRunnable):
    def __init__(
        self, controller, location, graph_id, q_unit, error_fraction,
        workspace_id, workspace_generation, batch_id, ordinal,
    ) -> None:
        super().__init__()
        self.controller = controller
        self.location = location
        self.graph_id = graph_id
        self.q_unit = q_unit
        self.error_fraction = error_fraction
        self.workspace_id = workspace_id
        self.workspace_generation = workspace_generation
        self.batch_id = batch_id
        self.ordinal = ordinal
        self.signals = WorkerSignals()
        self.cancelled = False

    def run(self) -> None:
        try:
            if self.cancelled:
                return
            record = self.controller.sources.load_location(
                self.location,
                q_unit=self.q_unit,
                error_fraction=self.error_fraction,
            )
            if not self.cancelled:
                self.signals.loaded.emit(record, self)
        except Exception as exc:
            self.signals.failed.emit(f"{self.location.display_name}: {exc}")
        finally:
            self.signals.finished.emit(self)


class GraphEditCommand(QUndoCommand):
    def __init__(self, window, before: GraphDocument, after: GraphDocument, recompute: bool, text: str):
        super().__init__(text)
        self.window = window
        self.before = before
        self.after = after
        self.recompute = recompute

    def redo(self) -> None:
        self.window._commit_graph(self.after, self.recompute)

    def undo(self) -> None:
        self.window._commit_graph(self.before, self.recompute)


class DatasetImportCommand(QUndoCommand):
    """One undoable import preserves both graph views and the dataset catalog."""

    def __init__(
        self, window, datasets, graph_id: str, transform_parameters=None, series_styles=None
    ) -> None:
        super().__init__("Import datasets")
        self.window = window
        self.datasets = tuple(datasets)
        self.graph_id = graph_id
        self.transform_parameters = transform_parameters
        self.series_styles = series_styles
        self.before = None
        self.after = None

    def redo(self) -> None:
        if self.after is None:
            self.before = self.window._controller_state()
            self.window.controller.add_datasets(
                self.datasets,
                graph_id=self.graph_id,
                transform_parameters=self.transform_parameters,
                series_styles=self.series_styles,
            )
            self.after = self.window._controller_state()
        else:
            self.window._restore_controller_state(self.after)
        self.window._render_graph(self.graph_id)
        self.window._refresh_dataset_list()
        self.window._sync_inspector()

    def undo(self) -> None:
        self.window._restore_controller_state(self.before)
        self.window._render_graph(self.graph_id)
        self.window._refresh_dataset_list()
        self.window._sync_inspector()


class WorkspaceEditCommand(QUndoCommand):
    """Undoable graph-tab lifecycle operation with snapshot restoration."""

    def __init__(self, window, text: str, action) -> None:
        super().__init__(text)
        self.window = window
        self.action = action
        self.before = None
        self.after = None

    def redo(self) -> None:
        if self.after is None:
            self.before = self.window._controller_state()
            self.action()
            self.after = self.window._controller_state()
        else:
            self.window._restore_controller_state(self.after)
        self.window._rebuild_tabs()

    def undo(self) -> None:
        self.window._restore_controller_state(self.before)
        self.window._rebuild_tabs()


class DatasetListWidget(QListWidget):
    """Dataset list that keeps internal reordering and accepts local file drops."""

    pathsDropped = Signal(object)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        # QAbstractItemView receives external drops through this scroll
        # area's viewport, not through the QListWidget itself.  This matters
        # especially when the list has no rows yet.
        self.setAcceptDrops(True)
        self.viewport().setAcceptDrops(True)

    @staticmethod
    def _local_paths(event) -> list[Path]:
        mime_data = event.mimeData()
        if not mime_data.hasUrls():
            return []
        return [Path(url.toLocalFile()) for url in mime_data.urls() if url.isLocalFile()]

    def _handle_external_drop(self, event) -> bool:
        paths = self._local_paths(event)
        if not paths:
            return False
        if event.type() == QEvent.Type.Drop:
            self.pathsDropped.emit(paths)
        event.acceptProposedAction()
        return True

    def dragEnterEvent(self, event) -> None:  # noqa: N802 - Qt API
        if self._handle_external_drop(event):
            return
        super().dragEnterEvent(event)

    def dragMoveEvent(self, event) -> None:  # noqa: N802 - Qt API
        if self._handle_external_drop(event):
            return
        super().dragMoveEvent(event)

    def dropEvent(self, event) -> None:  # noqa: N802 - Qt API
        if self._handle_external_drop(event):
            return
        super().dropEvent(event)

    def viewportEvent(self, event) -> bool:  # noqa: N802 - Qt API
        if event.type() in (QEvent.Type.DragEnter, QEvent.Type.DragMove, QEvent.Type.Drop):
            if self._handle_external_drop(event):
                return True
        return super().viewportEvent(event)


class MainWindow(QMainWindow):
    newWindowRequested = Signal()
    openWorkspaceRequested = Signal(object)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Bernardyn")
        self.resize(1500, 900)
        self.controller = ApplicationController()
        self.renderers = builtin_renderers()
        self.thread_pool = QThreadPool.globalInstance()
        self._workers: set[SourceLoadWorker] = set()
        self._load_batches: dict[int, dict] = {}
        self._next_load_batch_id = 0
        self._output_previews: list[OutputPreviewDialog] = []
        self._pending_graph_renders: set[str] = set()
        self._refreshing_dataset_list = False
        self._startup_restore_pending = True
        self.user_state = UserState()
        self._workspace_lock: QLockFile | None = None
        self._locked_workspace_path: Path | None = None
        self.undo_stack = QUndoStack(self)
        self.tabs = QTabWidget(self)
        self.tabs.setTabsClosable(True)
        self.tabs.currentChanged.connect(self._active_tab_changed)
        self.tabs.tabCloseRequested.connect(self._close_tab)
        self.setCentralWidget(self.tabs)
        self.dataset_list = DatasetListWidget(self)
        self.dataset_list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.dataset_list.setDragDropMode(QAbstractItemView.DragDropMode.DragDrop)
        self.dataset_list.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.dataset_list.setDragEnabled(True)
        self.dataset_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.dataset_list.pathsDropped.connect(self._dropped_data_paths)
        self.dataset_list.customContextMenuRequested.connect(self._dataset_context_menu)
        self.dataset_list.model().rowsMoved.connect(
            lambda *_: QTimer.singleShot(0, self._dataset_list_reordered)
        )
        self.inspector = InspectorWidget(self.controller.transforms, self)
        self.inspector.graphChanged.connect(self._queue_graph_change)
        self.inspector.transformRequested.connect(self._set_transform)
        self.inspector.resetRequested.connect(self._reset_graph_defaults)
        self.inspector.outputPreviewRequested.connect(self._preview_output)
        self.inspector.autoscaleRequested.connect(self._autoscale_current_graph)
        self.inspector.displayCanvasRequested.connect(self._set_display_canvas_size)
        self._build_docks()
        self._build_actions()
        self._build_menus()
        self.statusBar().showMessage("Ready")
        self._rebuild_tabs()

    def _build_docks(self) -> None:
        self.datasets_dock = QDockWidget("Data browser — active graph", self)
        self.datasets_dock.setObjectName("datasetsDock")
        data_widget = QWidget(self.datasets_dock)
        layout = QVBoxLayout(data_widget)
        filter_row = QHBoxLayout()
        filter_row.addWidget(QLabel("Show:", data_widget))
        self.dataset_filter = QComboBox(data_widget)
        for label, filter_id in DATASET_FILTERS:
            self.dataset_filter.addItem(label, filter_id)
        self.dataset_filter.setToolTip("Filter the data shown in this graph without changing the graph.")
        self.dataset_filter.currentIndexChanged.connect(self._refresh_dataset_list)
        filter_row.addWidget(self.dataset_filter, 1)
        layout.addLayout(filter_row)
        open_button = QPushButton("Open data…", data_widget)
        open_button.clicked.connect(self._open_data)
        open_folder_button = QPushButton("Open folder…", data_widget)
        open_folder_button.clicked.connect(self._open_folder)
        add_catalog_button = QPushButton("Add from workspace…", data_widget)
        add_catalog_button.clicked.connect(self._add_from_workspace)
        add_results_button = QPushButton("Add pyIrena results…", data_widget)
        add_results_button.clicked.connect(self._add_pyirena_results)
        remove_button = QPushButton("Remove selected from graph", data_widget)
        remove_button.clicked.connect(self._remove_datasets)
        cancel_button = QPushButton("Cancel loading", data_widget)
        cancel_button.clicked.connect(self._cancel_loading)
        button_grid = QGridLayout()
        button_grid.addWidget(open_button, 0, 0)
        button_grid.addWidget(open_folder_button, 0, 1)
        button_grid.addWidget(add_catalog_button, 1, 0)
        button_grid.addWidget(add_results_button, 1, 1)
        layout.addLayout(button_grid)
        layout.addWidget(self.dataset_list, 1)
        action_grid = QGridLayout()
        action_grid.addWidget(remove_button, 0, 0)
        action_grid.addWidget(cancel_button, 0, 1)
        layout.addLayout(action_grid)
        self.datasets_dock.setWidget(data_widget)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self.datasets_dock)

        self.inspector_dock = QDockWidget("Graph inspector", self)
        self.inspector_dock.setObjectName("graphInspectorDock")
        inspector_widget = QWidget(self.inspector_dock)
        inspector_layout = QVBoxLayout(inspector_widget)
        inspector_layout.setContentsMargins(6, 6, 6, 0)
        self.documentation_button = QPushButton("Documentation", inspector_widget)
        self.documentation_button.setToolTip(
            "Open local documentation (or GitHub documentation after PyPI installation)"
        )
        self.documentation_button.setStyleSheet(
            "QPushButton { background: #c62828; color: white; font-weight: bold; "
            "border: 1px solid #8e0000; border-radius: 4px; padding: 3px 10px; } "
            "QPushButton:hover { background: #e53935; }"
        )
        self.documentation_button.clicked.connect(self._open_documentation)
        inspector_layout.addWidget(
            self.documentation_button, 0, Qt.AlignmentFlag.AlignRight
        )
        inspector_layout.addWidget(self.inspector, 1)
        self.inspector_dock.setWidget(inspector_widget)
        self.inspector_dock.setMinimumWidth(340)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.inspector_dock)

    def _action(self, text, slot, shortcut=None) -> QAction:
        action = QAction(text, self)
        action.triggered.connect(slot)
        if shortcut:
            action.setShortcut(shortcut)
        return action

    def _build_actions(self) -> None:
        self.new_workspace_action = self._action("New workspace", self._new_workspace, QKeySequence.StandardKey.New)
        self.new_window_action = self._action("New window", self.newWindowRequested.emit)
        self.open_data_action = self._action("Open data…", self._open_data, QKeySequence.StandardKey.Open)
        self.open_folder_action = self._action("Open folder…", self._open_folder, "Ctrl+Shift+F")
        self.browse_datasets_action = self._action("Browse data sets…", self._browse_datasets)
        self.workspace_properties_action = self._action(
            "Workspace properties…", self._workspace_properties
        )
        self.open_package_action = self._action("Open package…", self._open_package, "Ctrl+Shift+O")
        self.open_package_new_window_action = self._action(
            "Open workspace in new window…", self._open_package_in_new_window
        )
        self.import_graph_action = self._action("Import graph from package…", self._import_graph)
        self.save_action = self._action("Save", self._save, QKeySequence.StandardKey.Save)
        self.save_as_action = self._action("Save workspace package as…", self._save_workspace_as, QKeySequence.StandardKey.SaveAs)
        self.save_graph_action = self._action("Save graph package…", self._save_graph)
        self.export_image_action = self._action("Export image…", self._export_image, "Ctrl+E")
        self.output_preview_action = self._action("Preview output…", self._preview_output)
        self.print_action = self._action("Print graph…", self._print_graph, QKeySequence.StandardKey.Print)
        self.export_csv_action = self._action("Export displayed data as CSV…", self._export_csv)
        self.export_itx_action = self._action("Export displayed data as Igor ITX…", self._export_itx)
        self.export_h5xp_action = self._action("Export canonical data to Igor h5xp…", self._export_h5xp)
        self.copy_action = self._action("Copy graph image", self._copy_graph, QKeySequence.StandardKey.Copy)
        self.new_2d_action = self._action(
            "New 2D graph", lambda: self._new_graph("plot2d"), "Ctrl+Shift+N"
        )
        self.new_waterfall_action = self._action("New 3D waterfall", lambda: self._new_graph("opengl_waterfall"))
        self.new_surface_action = self._action("New 3D surface", lambda: self._new_graph("opengl_surface"))
        self.recompute_action = self._action("Recompute with current version", self._recompute_graph)
        self.reset_graph_action = self._action("Reset graph to defaults…", self._reset_graph_defaults)
        self.color_preset_action = self._action(
            "Color preset", lambda: self._apply_series_preset("color")
        )
        self.bw_preset_action = self._action(
            "Black and white preset", lambda: self._apply_series_preset("bw")
        )
        self.rainbow_preset_action = self._action(
            "Rainbow preset", lambda: self._apply_series_preset("rainbow")
        )
        self.save_template_action = self._action("Save graph template…", self._save_template)
        self.apply_template_action = self._action("Apply graph template…", self._apply_template)
        self.delete_template_action = self._action("Delete graph template…", self._delete_template)
        self.undo_action = self.undo_stack.createUndoAction(self, "Undo")
        self.undo_action.setShortcut(QKeySequence.StandardKey.Undo)
        self.redo_action = self.undo_stack.createRedoAction(self, "Redo")
        self.redo_action.setShortcut(QKeySequence.StandardKey.Redo)
        self.reopen_data_browser_action = self._action(
            "Open Data Browser", lambda: self._reopen_dock(self.datasets_dock, Qt.DockWidgetArea.LeftDockWidgetArea)
        )
        self.reopen_inspector_action = self._action(
            "Open Graph Inspector", lambda: self._reopen_dock(self.inspector_dock, Qt.DockWidgetArea.RightDockWidgetArea)
        )
        self.reset_panels_action = self._action("Reset panel layout", self._reset_panel_layout)

    def _build_menus(self) -> None:
        file_menu = self.menuBar().addMenu("&File")
        for action in (
            self.new_workspace_action, self.new_window_action, self.workspace_properties_action,
            self.open_data_action, self.open_folder_action, self.browse_datasets_action,
            self.open_package_action, self.open_package_new_window_action,
        ):
            file_menu.addAction(action)
        self.recent_workspaces_menu = file_menu.addMenu("Recent workspaces")
        self.recent_workspaces_menu.aboutToShow.connect(self._populate_recent_workspaces_menu)
        file_menu.addSeparator()
        for action in (
            self.import_graph_action, None, self.save_action, self.save_as_action,
            self.save_graph_action, None, self.export_image_action, self.copy_action,
            self.print_action, self.output_preview_action, self.export_csv_action,
            self.export_itx_action, self.export_h5xp_action,
        ):
            file_menu.addSeparator() if action is None else file_menu.addAction(action)
        edit_menu = self.menuBar().addMenu("&Edit")
        edit_menu.addActions([self.undo_action, self.redo_action, self.copy_action])
        graph_menu = self.menuBar().addMenu("&Graph")
        graph_menu.addActions(
            [
                self.new_2d_action,
                self.new_waterfall_action,
                self.new_surface_action,
                self.recompute_action,
                self.output_preview_action,
                self.reset_graph_action,
            ]
        )
        preset_menu = graph_menu.addMenu("Series presets")
        preset_menu.addActions(
            [self.color_preset_action, self.bw_preset_action, self.rainbow_preset_action]
        )
        template_menu = self.menuBar().addMenu("&Templates")
        template_menu.addActions(
            [self.save_template_action, self.apply_template_action, self.delete_template_action]
        )
        view_menu = self.menuBar().addMenu("&View")
        view_menu.addActions(
            [self.reopen_data_browser_action, self.reopen_inspector_action, self.reset_panels_action]
        )

    def _reopen_dock(self, dock: QDockWidget, area: Qt.DockWidgetArea) -> None:
        """Recover a panel that was closed or floated beyond a screen edge."""
        dock.setFloating(False)
        self.addDockWidget(area, dock)
        dock.show()
        dock.raise_()

    def _reset_panel_layout(self) -> None:
        """Put the two essential controls back in their safe default places."""
        self._reopen_dock(self.datasets_dock, Qt.DockWidgetArea.LeftDockWidgetArea)
        self._reopen_dock(self.inspector_dock, Qt.DockWidgetArea.RightDockWidgetArea)

    def _open_documentation(self) -> None:
        documentation_url = _documentation_url()
        if not QDesktopServices.openUrl(documentation_url):
            QMessageBox.warning(
                self,
                "Documentation",
                f"Could not open documentation:\n{documentation_url.toString()}",
            )

    def _current_page(self):
        return self.tabs.currentWidget()

    def _current_graph(self) -> GraphDocument | None:
        page = self._current_page()
        if page is None or not hasattr(page, "graph_id"):
            return None
        try:
            return self.controller.workspace.graph(page.graph_id)
        except KeyError:
            return None

    @property
    def workspace_path(self) -> Path | None:
        """The editable package associated with this window, if it has one."""
        return self.controller.package_path

    def _try_lock_workspace(self, path: str | Path) -> tuple[QLockFile | None, bool]:
        """Acquire an edit lock, returning whether this call acquired it."""
        target = Path(path).expanduser().resolve()
        if self._locked_workspace_path == target and self._workspace_lock is not None:
            return self._workspace_lock, False
        lock = QLockFile(f"{target}.lock")
        # QLockFile identifies a dead local process and cleans a stale lock;
        # 30 seconds also covers a crash on filesystems where that check is not
        # available immediately.
        lock.setStaleLockTime(30_000)
        if lock.tryLock(0):
            return lock, True
        return None, False

    def _release_workspace_lock(self) -> None:
        if self._workspace_lock is not None:
            self._workspace_lock.unlock()
        self._workspace_lock = None
        self._locked_workspace_path = None

    def _workspace_locked_message(self, path: Path) -> str:
        return (
            f"{path.name} is already open for editing in another Bernardyn window or process.\n\n"
            "To prevent one save from silently overwriting the other, Bernardyn will not open "
            "a second editable copy. Open a different workspace or use Save As to make a copy."
        )

    def open_workspace(
        self,
        path: str | Path,
        *,
        remember: bool = True,
        restore_layout: bool = True,
        show_errors: bool = True,
    ) -> bool:
        """Open one package after acquiring its lifetime edit lock."""
        target = Path(path).expanduser().resolve()
        lock, acquired = self._try_lock_workspace(target)
        if lock is None:
            if show_errors:
                QMessageBox.warning(self, "Workspace already open", self._workspace_locked_message(target))
            else:
                self.statusBar().showMessage(f"Previous workspace is already open: {target.name}", 5000)
            return False
        try:
            loaded = self.controller.open_package(target)
        except Exception as exc:
            if acquired:
                lock.unlock()
            if show_errors:
                QMessageBox.critical(self, "Open package", str(exc))
                return False
            raise
        previous_lock = self._workspace_lock
        previous_path = self._locked_workspace_path
        self._workspace_lock = lock
        self._locked_workspace_path = target
        if previous_lock is not None and previous_lock is not lock and previous_path != target:
            previous_lock.unlock()
        self.undo_stack.clear()
        self._rebuild_tabs()
        if remember:
            self._remember_workspace(target)
        if loaded.warnings:
            QMessageBox.warning(self, "Package warnings", "\n".join(loaded.warnings))
        if restore_layout:
            self._restore_layout()
        return True

    def _new_workspace(self) -> None:
        if not self._confirm_discard():
            return
        self._release_workspace_lock()
        self.controller.new_workspace()
        self._pending_graph_renders.clear()
        self.undo_stack.clear()
        self._rebuild_tabs()

    def _remember_workspace(self, path: str | Path) -> None:
        """Store the last full workspace without putting it in the package."""
        resolved = str(Path(path).resolve())
        existing = self.user_state.get(RECENT_WORKSPACES_KEY, [])
        paths = existing if isinstance(existing, list) else []
        recent = [resolved]
        for item in paths:
            try:
                candidate = str(Path(item).expanduser().resolve())
            except (OSError, TypeError):
                continue
            if candidate != resolved and candidate not in recent:
                recent.append(candidate)
        self.user_state.set(LAST_WORKSPACE_PATH_KEY, resolved)
        self.user_state.set(RECENT_WORKSPACES_KEY, recent[:RECENT_WORKSPACES_LIMIT])
        self.user_state.save()

    def _populate_recent_workspaces_menu(self) -> None:
        self.recent_workspaces_menu.clear()
        saved = self.user_state.get(RECENT_WORKSPACES_KEY, [])
        entries = saved if isinstance(saved, list) else []
        valid: list[Path] = []
        for item in entries:
            try:
                path = Path(item).expanduser().resolve()
            except (OSError, TypeError):
                continue
            if path.is_file() and path not in valid:
                valid.append(path)
        if [str(path) for path in valid] != entries:
            self.user_state.set(RECENT_WORKSPACES_KEY, [str(path) for path in valid])
            if self.user_state.get(LAST_WORKSPACE_PATH_KEY) not in {str(path) for path in valid}:
                self.user_state.set(LAST_WORKSPACE_PATH_KEY, str(valid[0]) if valid else "")
            self.user_state.save()
        if not valid:
            empty = self.recent_workspaces_menu.addAction("No recent workspaces")
            empty.setEnabled(False)
            return
        for path in valid:
            action = self.recent_workspaces_menu.addAction(f"{path.name} — {path.parent}")
            action.setToolTip(str(path))
            action.triggered.connect(
                lambda _checked=False, selected=path: self.openWorkspaceRequested.emit(selected)
            )
        self.recent_workspaces_menu.addSeparator()
        self.recent_workspaces_menu.addAction("Clear recent workspaces", self._clear_recent_workspaces)

    def _clear_recent_workspaces(self) -> None:
        self.user_state.set(RECENT_WORKSPACES_KEY, [])
        self.user_state.set(LAST_WORKSPACE_PATH_KEY, "")
        self.user_state.save()

    def restore_last_workspace(self) -> None:
        """Open the last successfully saved or opened workspace at startup."""
        if not self._startup_restore_pending:
            return
        self._startup_restore_pending = False
        saved_path = self.user_state.get(LAST_WORKSPACE_PATH_KEY)
        if not saved_path:
            return
        path = Path(saved_path).expanduser()
        if not path.is_file():
            # Do not repeatedly try a workspace that has been moved or deleted.
            self.user_state.set(LAST_WORKSPACE_PATH_KEY, "")
            self.user_state.save()
            return
        try:
            if self.open_workspace(path, remember=True, restore_layout=True, show_errors=False):
                self.statusBar().showMessage(f"Reopened {path.name}", 5000)
        except Exception:
            # A corrupt or unsupported package should never make every launch
            # fail. Forget it and leave the normal empty workspace available.
            log.warning("could not reopen last workspace %s", path, exc_info=True)
            self.user_state.set(LAST_WORKSPACE_PATH_KEY, "")
            self.user_state.save()
            self.statusBar().showMessage("Could not reopen the previous workspace.", 5000)

    def _workspace_properties(self) -> None:
        title, ok = QInputDialog.getText(
            self,
            "Workspace properties",
            "Package title:",
            text=self.controller.workspace.title,
        )
        if not ok:
            return
        description, ok = QInputDialog.getMultiLineText(
            self,
            "Workspace properties",
            "Package description:",
            self.controller.workspace.description,
        )
        if not ok:
            return
        self.controller.workspace.title = title
        self.controller.workspace.description = description
        self.controller.workspace.dirty = True

    def _new_graph(self, renderer_id: str) -> None:
        self.undo_stack.push(
            WorkspaceEditCommand(self, "New graph", lambda: self.controller.new_graph(renderer_id))
        )

    def _close_tab(self, index: int) -> None:
        page = self.tabs.widget(index)
        if not isinstance(page, GraphPage):
            self.tabs.removeTab(index)
            return
        self.undo_stack.push(
            WorkspaceEditCommand(
                self, "Close graph", lambda: self.controller.close_graph(page.graph_id)
            )
        )

    def _active_tab_changed(self, index: int) -> None:
        page = self.tabs.widget(index)
        if isinstance(page, GraphPage):
            self.controller.workspace.active_graph_id = page.graph_id
        self._refresh_dataset_list()
        self._sync_inspector()

    def _rebuild_tabs(self) -> None:
        while self.tabs.count():
            widget = self.tabs.widget(0)
            self.tabs.removeTab(0)
            widget.deleteLater()
        if not self.controller.workspace.graphs and self.controller.previews:
            for graph_id, png in self.controller.previews.items():
                self.tabs.addTab(PreviewPage(graph_id, png, self), "Archived preview")
        else:
            for graph in self.controller.workspace.graphs:
                try:
                    self.renderers.get(graph.renderer_id)
                    unknown_renderer = False
                except KeyError:
                    unknown_renderer = True
                    if graph.id in self.controller.previews:
                        self.controller.preview_only_graphs.add(graph.id)
                if graph.id in self.controller.preview_only_graphs and graph.id in self.controller.previews:
                    page = PreviewPage(graph.id, self.controller.previews[graph.id], self)
                    self.tabs.addTab(page, f"{graph.title} (preview)")
                else:
                    if unknown_renderer:
                        self.statusBar().showMessage(
                            f"Unknown renderer {graph.renderer_id!r}; no embedded preview was available"
                        )
                    page = GraphPage(graph, self, renderers=self.renderers)
                    page.powerLawMoved.connect(self._move_power_law)
                    self.tabs.addTab(page, graph.title)
                    self._render_page(page, graph)
            active = self.controller.workspace.active_graph_id
            for index in range(self.tabs.count()):
                if getattr(self.tabs.widget(index), "graph_id", None) == active:
                    self.tabs.setCurrentIndex(index)
                    break
        self._refresh_dataset_list()
        self._sync_inspector()

    def _render_page(self, page: GraphPage, graph: GraphDocument) -> None:
        page.render(graph, self.controller.snapshots.get(graph.id, {}))
        messages: list[str] = []
        if page.fallback_reason:
            messages.append(f"OpenGL unavailable; showing 2D fallback: {page.fallback_reason}")
        # Curves, annotations and axis ranges are drawn independently.  Report
        # anything the renderer could not draw: Qt swallows exceptions raised
        # inside slots, so an unreported failure just looks like missing work.
        messages.extend(page.render_warnings)
        if messages:
            log.warning("; ".join(messages))
            self.statusBar().showMessage(" | ".join(messages))

    def _render_graph(self, graph_id: str) -> None:
        graph = self.controller.workspace.graph(graph_id)
        for index in range(self.tabs.count()):
            page = self.tabs.widget(index)
            if isinstance(page, GraphPage) and page.graph_id == graph_id:
                self._render_page(page, graph)
                self.tabs.setTabText(index, graph.title)
                return

    def _set_display_canvas_size(self, width: int, height: int) -> None:
        page = self.tabs.currentWidget()
        if not isinstance(page, GraphPage):
            return
        page.set_display_canvas_size(width, height)
        self.statusBar().showMessage(f"Set displayed canvas to {width} × {height} px")

    def _move_power_law(
        self, graph_id: str, annotation_id: str, position: tuple[float, float]
    ) -> None:
        """Persist a finished drag as an undoable annotation edit."""
        graph = self.controller.workspace.graph(graph_id)
        annotations = tuple(
            replace(annotation, position=position)
            if annotation.id == annotation_id
            else annotation
            for annotation in graph.annotations
        )
        if annotations == graph.annotations:
            return
        self._queue_graph_change(
            replace(graph, annotations=annotations), False, "Move power-law slope"
        )

    def _controller_state(self):
        """Capture immutable graph/data state for dataset-import undo."""
        return (
            replace(
                self.controller.workspace,
                datasets=dict(self.controller.workspace.datasets),
                graphs=list(self.controller.workspace.graphs),
            ),
            {graph_id: dict(values) for graph_id, values in self.controller.snapshots.items()},
            {graph_id: list(values) for graph_id, values in self.controller._graph_warnings.items()},
            dict(self.controller.previews),
            {graph_id: dict(values) for graph_id, values in self.controller.renderer_data.items()},
            set(self.controller.read_only_graphs),
            set(self.controller.preview_only_graphs),
        )

    def _restore_controller_state(self, state) -> None:
        (
            workspace,
            snapshots,
            graph_warnings,
            previews,
            renderer_data,
            read_only_graphs,
            preview_only_graphs,
        ) = state
        self.controller.workspace = workspace
        self.controller.snapshots = snapshots
        self.controller._graph_warnings = graph_warnings
        self.controller.previews = previews
        self.controller.renderer_data = renderer_data
        self.controller.read_only_graphs = read_only_graphs
        self.controller.preview_only_graphs = preview_only_graphs

    def _autoscale_current_graph(self) -> None:
        """Refit an already-auto graph after the user has zoomed it manually."""
        graph = self._current_graph()
        if graph is None:
            return
        for index in range(self.tabs.count()):
            page = self.tabs.widget(index)
            if isinstance(page, GraphPage) and page.graph_id == graph.id:
                autoscale = getattr(page.renderer, "autoscale", None)
                if autoscale is not None:
                    autoscale()
                return

    def _sync_inspector(self) -> None:
        graph = self._current_graph()
        warnings = self.controller.graph_warnings(graph.id) if graph else self.controller.warnings
        self.inspector.set_graph(
            graph,
            self.controller.workspace.datasets,
            warnings,
            snapshots=self.controller.snapshots.get(graph.id, {}) if graph else {},
            read_only=bool(
                graph
                and graph.id
                in (self.controller.read_only_graphs | self.controller.preview_only_graphs)
            ),
        )

    def _queue_graph_change(self, graph: GraphDocument, recompute: bool, text: str) -> None:
        try:
            before = self.controller.workspace.graph(graph.id)
            # Controller/API callers can update a graph while the inspector is
            # open.  Presentation controls must not turn that stale, empty
            # inspector copy into an accidental series deletion.
            if before.series and not graph.series:
                graph = replace(graph, series=before.series)
            self.controller.validate_graph_update(graph, recompute=recompute)
            self.undo_stack.push(GraphEditCommand(self, before, graph, recompute, text))
        except Exception as exc:
            QMessageBox.warning(self, "Graph change", str(exc))
            self._sync_inspector()

    def _commit_graph(self, graph: GraphDocument, recompute: bool) -> None:
        self.controller.update_graph(graph, recompute=recompute)
        self._render_graph(graph.id)
        self._refresh_dataset_list()
        self._sync_inspector()

    def _set_transform(self, transform_id: str) -> None:
        graph = self._current_graph()
        if graph is None:
            return
        transform = self.controller.transforms.get(transform_id)
        parameters: dict[str, dict[str, float]] = {item.id: {} for item in graph.series}
        if transform.parameters and graph.series:
            rows = []
            for item in graph.series:
                dataset = self.controller.workspace.datasets[item.dataset_id]
                initial = {
                    parameter.id: value
                    for parameter in transform.parameters
                    if (value := _metadata_number(dict(dataset.metadata), parameter.id))
                    is not None
                }
                rows.append((item.id, dataset.label, initial))
            dialog = SeriesTransformParameterDialog(transform, rows, self)
            if dialog.exec() != dialog.DialogCode.Accepted:
                self._sync_inspector()
                return
            parameters = dialog.values()
        before = graph
        series = tuple(
            replace(
                item,
                transform_id=transform_id,
                transform_parameters=parameters.get(item.id, {}),
            )
            for item in graph.series
        )
        after = replace(
            graph,
            view_transform_id=transform_id,
            series=series,
            x_axis=replace(graph.x_axis, label=transform.default_x_label, log=transform.default_x_log, auto_range=True),
            y_axis=replace(graph.y_axis, label=transform.default_y_label, log=transform.default_y_log, auto_range=True),
        )
        try:
            self.controller.validate_graph_update(after, recompute=True)
            self.undo_stack.push(GraphEditCommand(self, before, after, True, f"Set {transform.name} view"))
        except Exception as exc:
            QMessageBox.warning(self, "Graph change", str(exc))
            self._sync_inspector()

    def _open_data(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Open scattering data",
            str(self.user_state.get("last_data_folder", "")),
            "Scattering data (*.h5 *.hdf5 *.hdf *.nxs *.dat *.txt *.csv);;All files (*)",
        )
        if not paths:
            return
        selected_paths = [Path(value) for value in paths]
        self._open_file_selector(selected_paths[0].parent, selected_paths)

    def _browse_datasets(self) -> None:
        """Explicitly choose non-default SASdata groups from individual files."""
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Browse scattering data sets",
            str(self.user_state.get("last_data_folder", "")),
            "Scattering data (*.h5 *.hdf5 *.hdf *.nxs *.dat *.txt *.csv);;All files (*)",
        )
        if paths:
            self._open_data_paths([Path(value) for value in paths], use_preferred=False)

    def _open_folder(self) -> None:
        selected = QFileDialog.getExistingDirectory(
            self,
            "Open folder containing scattering data",
            str(self.user_state.get("last_data_folder", "")),
        )
        if not selected:
            return
        self._open_file_selector(Path(selected))

    def _add_from_workspace(self) -> None:
        graph = self._current_graph()
        if graph is None:
            return
        present = {view.dataset_id for view in graph.series}
        choices = [
            (f"{dataset.label} ({dataset.id[:8]})", dataset)
            for dataset in self.controller.workspace.datasets.values()
            if dataset.id not in present
        ]
        if not choices:
            self.statusBar().showMessage("All loaded datasets are already in this graph.", 3000)
            return
        label, accepted = QInputDialog.getItem(
            self, "Add from workspace", "Loaded dataset:", [item[0] for item in choices], 0, False
        )
        if not accepted:
            return
        dataset = next(dataset for item, dataset in choices if item == label)
        try:
            self.controller.validate_add_datasets((dataset,), graph_id=graph.id)
            self.undo_stack.push(DatasetImportCommand(self, (dataset,), graph.id))
        except Exception as exc:
            QMessageBox.warning(self, "Add from workspace", str(exc))

    def _dataset_context_menu(self, position) -> None:
        item = self.dataset_list.itemAt(position)
        if item is not None and not item.isSelected():
            self.dataset_list.clearSelection()
            item.setSelected(True)
        if not self.dataset_list.selectedItems():
            return
        menu = QMenu(self.dataset_list)
        menu.addAction("Copy selected to…", lambda: self._transfer_selected_series(move=False))
        menu.addAction("Move selected to…", lambda: self._transfer_selected_series(move=True))
        menu.exec(self.dataset_list.mapToGlobal(position))

    def _transfer_selected_series(self, *, move: bool) -> None:
        source = self._current_graph()
        series_ids = {
            item.data(Qt.ItemDataRole.UserRole) for item in self.dataset_list.selectedItems()
        }
        if source is None or not series_ids:
            return
        choices = [
            (f"{index}. {graph.title}", graph.id)
            for index, graph in enumerate(self.controller.workspace.graphs, start=1)
            if graph.id != source.id
        ]
        choices.insert(0, ("Create new 2D graph", None))
        verb = "Move" if move else "Copy"
        selected, accepted = QInputDialog.getItem(
            self,
            f"{verb} selected datasets",
            "Destination graph:",
            [label for label, _ in choices],
            0,
            False,
        )
        if not accepted:
            return
        target_id = next(graph_id for label, graph_id in choices if label == selected)
        try:
            if target_id is None:
                target = GraphDocument(
                    title=f"Scattering plot {len(self.controller.workspace.graphs) + 1}"
                )
                self.controller.validate_series_transfer(source.id, target, series_ids, move=move)

                def action() -> None:
                    self.controller.transfer_series_to_new_graph(
                        source.id, target, series_ids, move=move
                    )
            else:
                target = self.controller.workspace.graph(target_id)
                self.controller.validate_series_transfer(source.id, target, series_ids, move=move)

                def action() -> None:
                    self.controller.transfer_series(
                        source.id, target.id, series_ids, move=move
                    )
            self.undo_stack.push(WorkspaceEditCommand(self, f"{verb} datasets", action))
        except Exception as exc:
            QMessageBox.warning(self, f"{verb} datasets", str(exc))

    def _add_pyirena_results(self) -> None:
        graph = self._current_graph()
        if graph is None:
            return
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Add saved pyIrena results",
            str(self.user_state.get("last_data_folder", "")),
            "HDF5 / NeXus files (*.h5 *.hdf5 *.hdf *.nxs)",
        )
        selected_results = []
        for value in paths:
            try:
                descriptors = discover_results(value)
                if not descriptors:
                    QMessageBox.information(
                        self, "pyIrena results", f"No supported saved results in {Path(value).name}."
                    )
                    continue
                descriptor = descriptors[0]
                if len(descriptors) > 1:
                    title, accepted = QInputDialog.getItem(
                        self,
                        "Choose saved result",
                        f"Available in {Path(value).name}:",
                        [item.title for item in descriptors],
                        0,
                        False,
                    )
                    if not accepted:
                        continue
                    descriptor = next(item for item in descriptors if item.title == title)
                choices = [("Data + fit", "iq")]
                choices.extend(
                    ("Residuals", "residuals") if kind == "residuals" else ("Distribution", kind)
                    for kind in available_curve_kinds(descriptor)
                )
                choice, accepted = QInputDialog.getItem(
                    self,
                    "Choose result data",
                    f"Import from {descriptor.title}:",
                    [label for label, _ in choices],
                    0,
                    False,
                )
                if not accepted:
                    continue
                kind = next(kind for label, kind in choices if label == choice)
                selected_results.append(
                    (kind, load_result_bundle(descriptor) if kind == "iq" else load_result_curve(descriptor, kind))
                )
            except Exception as exc:
                QMessageBox.warning(self, "pyIrena results", f"{Path(value).name}: {exc}")
        if not selected_results:
            return
        try:
            if any(kind == "iq" for kind, _ in selected_results) and graph.view_transform_id != "raw":
                raise ValueError("Data + fit uses the General I(Q) view. Create or select an I(Q) graph first.")

            def action() -> None:
                iq_bundles = [bundle for kind, bundle in selected_results if kind == "iq"]
                if iq_bundles:
                    datasets = []
                    styles = []
                    for bundle_index, bundle in enumerate(iq_bundles):
                        color = PALETTE[(len(graph.series) + 2 * bundle_index) % len(PALETTE)]
                        datasets.extend(record.to_dataset() for record in bundle.records)
                        styles.extend(replace(style, color=color) for style in bundle.styles)
                    self.controller.add_datasets(datasets, graph_id=graph.id, series_styles=styles)
                for kind, bundle in selected_results:
                    if kind == "iq":
                        continue
                    target = self.controller.new_graph(title=bundle.graph_title)
                    target = replace(
                        target,
                        x_axis=AxisSpec(label=_axis_label(bundle.curve.x_label, bundle.curve.x_unit), log=bundle.x_log),
                        y_axis=AxisSpec(label=_axis_label(bundle.curve.y_label, bundle.curve.y_unit), log=bundle.y_log),
                    )
                    self.controller.update_graph(target)
                    self.controller.add_datasets(
                        (bundle.curve,), graph_id=target.id, series_styles=(bundle.style,)
                    )

            self.undo_stack.push(WorkspaceEditCommand(self, "Import pyIrena results", action))
            self.user_state.set("last_data_folder", str(Path(paths[0]).parent))
            self.user_state.save()
        except Exception as exc:
            QMessageBox.warning(self, "pyIrena results", str(exc))

    def _dropped_data_paths(self, dropped: list[Path]) -> None:
        """Open dropped files/folders through the normal profile-aware importer."""
        paths = [path for path in dropped if path.exists()]
        if not paths:
            self.statusBar().showMessage("No accessible files or folders were dropped.", 5000)
            return
        files_by_folder: dict[Path, list[Path]] = {}
        folders: list[Path] = []
        for path in paths:
            if path.is_dir():
                folders.append(path)
            elif path.is_file():
                files_by_folder.setdefault(path.parent, []).append(path)
        # The selector persists the chosen 1-D datasets by file layout.  A
        # selected file can therefore load immediately for a known layout,
        # while unfamiliar multi-dataset files always ask the user to choose.
        for folder in folders:
            self._open_file_selector(folder)
        for folder, files in files_by_folder.items():
            self._open_file_selector(folder, files)

    def _open_file_selector(self, folder: Path, paths: list[Path] | None = None) -> None:
        dialog = DataFileSelectorDialog(
            folder,
            self.controller.sources.discover_path,
            self.user_state.get("data_selector", {}),
            paths,
            self,
        )
        if dialog.exec() != dialog.DialogCode.Accepted:
            return
        self.user_state.set("last_data_folder", str(folder))
        self.user_state.set("data_selector", dialog.preferences())
        self.user_state.save()
        graph = self._current_graph()
        if graph is not None:
            self._queue_locations(
                dialog.selected_locations(),
                graph.id,
                dialog.q_unit.currentText(),
                dialog.error_fraction.value() / 100.0,
            )

    def _open_data_paths(self, paths: list[Path], *, use_preferred: bool) -> None:
        graph = self._current_graph()
        if graph is None:
            return
        q_unit = "1/A"
        error_fraction = 0.05
        text_paths = [path for path in paths if path.suffix.lower() in (".dat", ".txt", ".csv")]
        if text_paths:
            q_unit, ok = QInputDialog.getItem(
                self, "Text data Q unit", "Q unit for selected text data:",
                ["1/A", "1/nm", "1/pm", "1/um", "1/mm"], 0, False,
            )
            if not ok:
                return
            error_percent, ok = QInputDialog.getDouble(
                self,
                "Missing text uncertainty",
                "Synthesized intensity uncertainty for selected text data (%):",
                5.0,
                0.0001,
                100.0,
                3,
            )
            if not ok:
                return
            error_fraction = error_percent / 100.0
        locations_to_load = []
        for path in paths:
            try:
                locations = self.controller.sources.discover_path(path)
            except Exception as exc:
                if path.suffix.lower() in (".h5", ".hdf5", ".hdf", ".nxs"):
                    dialog = HDFMappingDialog(path, self)
                    if dialog.exec() != dialog.DialogCode.Accepted:
                        continue
                    locations = [dialog.location()]
                else:
                    QMessageBox.warning(self, "Data discovery", str(exc))
                    continue
            if use_preferred:
                locations = self.controller.sources.select_preferred_locations(locations)
            elif len(locations) > 1:
                dialog = LocationDialog(locations, self)
                if dialog.exec() != dialog.DialogCode.Accepted:
                    continue
                locations = dialog.selected()
            locations_to_load.extend(locations)
        if paths:
            self.user_state.set("last_data_folder", str(paths[0].parent))
            self.user_state.save()
        self._queue_locations(locations_to_load, graph.id, q_unit, error_fraction)

    def _queue_locations(
        self,
        locations,
        graph_id: str,
        q_unit: str,
        error_fraction: float,
    ) -> None:
        locations = list(locations)
        if not locations:
            return
        self._next_load_batch_id += 1
        batch_id = self._next_load_batch_id
        batch = {
            "workspace_id": self.controller.workspace.id,
            "workspace_generation": self.controller.workspace_generation,
            "graph_id": graph_id,
            "workers": set(),
            "finished": set(),
            "records": {},
        }
        self._load_batches[batch_id] = batch
        for ordinal, location in enumerate(locations):
            worker = SourceLoadWorker(
                self.controller, location, graph_id, q_unit, error_fraction,
                batch["workspace_id"], batch["workspace_generation"], batch_id, ordinal,
            )
            batch["workers"].add(worker)
            worker.signals.loaded.connect(self._source_loaded)
            worker.signals.failed.connect(
                lambda message: QMessageBox.warning(self, "Load error", message)
            )
            worker.signals.finished.connect(self._worker_finished)
            self._workers.add(worker)
            self.thread_pool.start(worker)
        self.statusBar().showMessage("Loading data…")

    def _source_loaded(self, record, worker: SourceLoadWorker) -> None:
        batch = self._load_batches.get(worker.batch_id)
        if batch is None or worker.cancelled:
            return
        # Defer mutations until every selected source completes.  This keeps
        # selection order and makes the batch a single undoable operation.
        batch["records"][worker.ordinal] = record

    def _worker_finished(self, worker) -> None:
        self._workers.discard(worker)
        batch = self._load_batches.get(worker.batch_id)
        if batch is not None:
            batch["finished"].add(worker)
            if batch["finished"] == batch["workers"]:
                self._load_batches.pop(worker.batch_id, None)
                current = self.controller.workspace
                graph_id = batch["graph_id"]
                target_is_current = (
                    not worker.cancelled
                    and current.id == batch["workspace_id"]
                    and self.controller.workspace_generation == batch["workspace_generation"]
                    and any(graph.id == graph_id for graph in current.graphs)
                )
                if target_is_current and batch["records"]:
                    datasets = [
                        batch["records"][ordinal].to_dataset()
                        for ordinal in sorted(batch["records"])
                    ]
                    try:
                        transform = self.controller.transforms.get(
                            current.graph(graph_id).view_transform_id
                        )
                        parameter_rows = []
                        needs_prompt = False
                        for dataset in datasets:
                            initial = {
                                parameter.id: value
                                for parameter in transform.parameters
                                if (value := _metadata_number(dict(dataset.metadata), parameter.id))
                                is not None
                            }
                            needs_prompt |= any(
                                parameter.required and parameter.id not in initial
                                for parameter in transform.parameters
                            )
                            parameter_rows.append((dataset.id, dataset.label, initial))
                        parameters = None
                        if needs_prompt:
                            dialog = SeriesTransformParameterDialog(transform, parameter_rows, self)
                            if dialog.exec() != dialog.DialogCode.Accepted:
                                self.statusBar().showMessage("Data import cancelled", 3000)
                                return
                            values = dialog.values()
                            parameters = [values[dataset.id] for dataset in datasets]
                        self.controller.validate_add_datasets(
                            datasets, graph_id=graph_id, transform_parameters=parameters
                        )
                        self.undo_stack.push(
                            DatasetImportCommand(self, datasets, graph_id, parameters)
                        )
                        self._pending_graph_renders.add(graph_id)
                        self.statusBar().showMessage(f"Loaded {len(datasets)} dataset(s)", 5000)
                    except Exception as exc:
                        QMessageBox.warning(self, "Load error", str(exc))
        if not self._workers:
            for graph_id in self._pending_graph_renders:
                self._render_graph(graph_id)
            self._pending_graph_renders.clear()
            self._refresh_dataset_list()
            self._sync_inspector()
            self.statusBar().showMessage("Ready", 2000)

    def _cancel_loading(self) -> None:
        for worker in self._workers:
            worker.cancelled = True
        self.statusBar().showMessage("Cancelling data loads…", 3000)

    def _refresh_dataset_list(self) -> None:
        graph = self._current_graph()
        selected = {item.data(Qt.ItemDataRole.UserRole) for item in self.dataset_list.selectedItems()}
        filter_id = self.dataset_filter.currentData()
        self.dataset_list.setDragEnabled(filter_id == "all")
        self._refreshing_dataset_list = True
        try:
            self.dataset_list.clear()
            if graph is None:
                return
            for index, series in enumerate(graph.series, start=1):
                dataset = self.controller.workspace.datasets[series.dataset_id]
                if not matches_dataset_filter(dataset, filter_id):
                    continue
                item = QListWidgetItem(f"{index}. {dataset.label}  ({dataset.point_count:,} points)")
                item.setData(Qt.ItemDataRole.UserRole, series.id)
                item.setToolTip(
                    "Drag to change plot order. Select and remove to hide this data from the graph."
                    if filter_id == "all"
                    else "Select to copy, move, or remove this filtered dataset from the graph."
                )
                self.dataset_list.addItem(item)
                if series.id in selected:
                    item.setSelected(True)
        finally:
            self._refreshing_dataset_list = False

    def _remove_datasets(self) -> None:
        graph = self._current_graph()
        series_ids = {item.data(Qt.ItemDataRole.UserRole) for item in self.dataset_list.selectedItems()}
        if graph is None or not series_ids:
            return
        retained = tuple(series for series in graph.series if series.id not in series_ids)
        self.undo_stack.push(
            GraphEditCommand(self, graph, replace(graph, series=retained), True, "Remove datasets")
        )

    def _dataset_list_reordered(self) -> None:
        if self._refreshing_dataset_list:
            return
        graph = self._current_graph()
        if graph is None:
            return
        order = [
            self.dataset_list.item(index).data(Qt.ItemDataRole.UserRole)
            for index in range(self.dataset_list.count())
        ]
        if set(order) != {series.id for series in graph.series}:
            return
        reordered = tuple(
            next(series for series in graph.series if series.id == series_id) for series_id in order
        )
        if reordered == graph.series:
            return
        self.undo_stack.push(
            GraphEditCommand(self, graph, graph.replace_series(reordered), False, "Reorder datasets")
        )

    def _open_package(self) -> None:
        previous = self.user_state.get(LAST_WORKSPACE_PATH_KEY, "")
        initial_folder = str(Path(previous).expanduser().parent) if previous else ""
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Open Bernardyn package",
            initial_folder,
            "Bernardyn (*.bernardyn.h5);;HDF5 (*.h5)",
        )
        if not path or not self._confirm_discard():
            return
        self.open_workspace(path)

    def _open_package_in_new_window(self) -> None:
        previous = self.user_state.get(LAST_WORKSPACE_PATH_KEY, "")
        initial_folder = str(Path(previous).expanduser().parent) if previous else ""
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Open Bernardyn package in new window",
            initial_folder,
            "Bernardyn (*.bernardyn.h5);;HDF5 (*.h5)",
        )
        if path:
            self.openWorkspaceRequested.emit(Path(path))

    def _import_graph(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Import graph", "", "Bernardyn (*.bernardyn.h5);;HDF5 (*.h5)")
        if not path:
            return
        try:
            package = load_package(path)
            if not package.workspace.graphs:
                raise ValueError("the package contains no editable graphs")
            dialog = GraphSelectionDialog(
                [(graph.id, graph.title) for graph in package.workspace.graphs], self
            )
            if dialog.exec() != dialog.DialogCode.Accepted:
                return
            selected = dialog.selected_ids()
            if not selected:
                return
            self.controller.import_from_package(path, selected)
            self._rebuild_tabs()
        except Exception as exc:
            QMessageBox.critical(self, "Import graph", str(exc))

    def _collect_artifacts(self):
        previews = dict(self.controller.previews)
        renderer_data = dict(self.controller.renderer_data)
        for index in range(self.tabs.count()):
            page = self.tabs.widget(index)
            if isinstance(page, GraphPage):
                try:
                    update = page.current_renderer_config()
                    if update:
                        graph = self.controller.workspace.graph(page.graph_id)
                        config = {**graph.renderer_config, **update}
                        self.controller.update_graph(replace(graph, renderer_config=config))
                    previews[page.graph_id] = page.capture_preview()
                    data = page.renderer_data()
                    if data:
                        renderer_data[page.graph_id] = data
                except Exception:
                    log.exception("could not capture graph preview")
        state = {
            "window_state": base64.b64encode(self.saveState()).decode("ascii"),
            "geometry": base64.b64encode(self.saveGeometry()).decode("ascii"),
        }
        self.controller.workspace.layout_state = json.dumps(state)
        return previews, renderer_data

    def _save(self) -> bool:
        if self.controller.package_path is None:
            return self._save_workspace_as()
        return self._save_to(self.controller.package_path)

    def _save_workspace_as(self) -> bool:
        previous = self.user_state.get(LAST_WORKSPACE_PATH_KEY, "")
        initial_path = str(Path(previous).expanduser()) if previous else "workspace.bernardyn.h5"
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Save workspace package",
            initial_path,
            "Bernardyn (*.bernardyn.h5)",
        )
        return bool(path) and self._save_to(path)

    def _save_graph(self) -> bool:
        graph = self._current_graph()
        if graph is None:
            return False
        path, _ = QFileDialog.getSaveFileName(self, "Save graph package", f"{graph.title}.bernardyn.h5", "Bernardyn (*.bernardyn.h5)")
        return bool(path) and self._save_to(path, graph_ids=[graph.id])

    def _save_to(self, path, graph_ids=None) -> bool:
        target = ensure_package_suffix(path).resolve()
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            QMessageBox.critical(self, "Save package", str(exc))
            return False
        lock, acquired = self._try_lock_workspace(target)
        if lock is None:
            QMessageBox.warning(self, "Workspace already open", self._workspace_locked_message(target))
            return False
        try:
            previews, renderer_data = self._collect_artifacts()
            saved = self.controller.save(
                target, graph_ids=graph_ids, previews=previews, renderer_data=renderer_data
            )
            if graph_ids is None:
                previous_lock = self._workspace_lock
                previous_path = self._locked_workspace_path
                self._workspace_lock = lock
                self._locked_workspace_path = saved
                if previous_lock is not None and previous_lock is not lock and previous_path != saved:
                    previous_lock.unlock()
                self._remember_workspace(saved)
            elif acquired:
                lock.unlock()
            self.statusBar().showMessage(f"Saved {saved.name}", 5000)
            return True
        except Exception as exc:
            if acquired:
                lock.unlock()
            QMessageBox.critical(self, "Save package", str(exc))
            return False

    def _export_image(self) -> None:
        page = self._current_page()
        if not isinstance(page, GraphPage):
            return
        graph = self._current_graph()
        is_3d = bool(graph and graph.renderer_id.startswith("opengl"))
        filter_value = "Images (*.png *.jpg *.jpeg)" if is_3d else "Images (*.png *.jpg *.jpeg *.svg)"
        path, _ = QFileDialog.getSaveFileName(self, "Export graph image", "graph.png", filter_value)
        if path:
            try:
                page.save_image(path)
            except Exception as exc:
                QMessageBox.critical(self, "Export image", str(exc))

    def _copy_graph(self) -> None:
        page = self._current_page()
        if isinstance(page, GraphPage):
            page.copy_to_clipboard()
            self.statusBar().showMessage("Graph image copied to the clipboard", 3000)

    def _preview_output(self) -> None:
        page = self._current_page()
        graph = self._current_graph()
        if not isinstance(page, GraphPage) or graph is None:
            return
        try:
            image = page.output_preview_image()
        except Exception as exc:
            QMessageBox.critical(self, "Preview output", str(exc))
            return
        dialog = OutputPreviewDialog(image, graph.title, self)
        dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        dialog.destroyed.connect(
            lambda *_: self._output_previews.remove(dialog)
            if dialog in self._output_previews
            else None
        )
        self._output_previews.append(dialog)
        dialog.show()

    def _print_graph(self) -> None:
        page = self._current_page()
        if not isinstance(page, GraphPage):
            return
        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        dialog = QPrintDialog(printer, self)
        if dialog.exec() != dialog.DialogCode.Accepted:
            return
        try:
            page.print_to(printer)
        except Exception as exc:
            QMessageBox.critical(self, "Print graph", str(exc))

    def _reset_graph_defaults(self) -> None:
        graph = self._current_graph()
        if graph is None:
            return
        answer = QMessageBox.question(
            self,
            "Reset graph to defaults",
            "Reset graph settings, axes, legend, annotations, and background?\n"
            "Loaded datasets and their curve styles will be kept.",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        defaults = GraphDocument(
            id=graph.id,
            title=graph.title,
            renderer_id=graph.renderer_id,
            series=graph.series,
            description=graph.description,
            notes=graph.notes,
        )
        self.undo_stack.push(GraphEditCommand(self, graph, defaults, True, "Reset graph to defaults"))

    def _export_csv(self) -> None:
        page = self._current_page()
        if not isinstance(page, GraphPage):
            return
        path, _ = QFileDialog.getSaveFileName(self, "Export displayed data", "graph.csv", "CSV (*.csv)")
        if path:
            try:
                page.export_csv(path)
            except Exception as exc:
                QMessageBox.critical(self, "Export data", str(exc))

    def _export_itx(self) -> None:
        page = self._current_page()
        if not isinstance(page, GraphPage):
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Export displayed data", "graph.itx", "Igor Text (*.itx)"
        )
        if path:
            try:
                page.export_itx(path)
            except Exception as exc:
                QMessageBox.critical(self, "Export data", str(exc))

    def _export_h5xp(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Export canonical data to Igor", "bernardyn_data.h5xp", "Igor HDF5 experiment (*.h5xp)")
        if path:
            try:
                export_datasets_to_h5xp(path, self.controller.workspace)
            except Exception as exc:
                QMessageBox.critical(self, "Igor export", str(exc))

    def _recompute_graph(self) -> None:
        graph = self._current_graph()
        if graph is None:
            return
        try:
            self.controller.recompute_graph(graph.id)
            self._render_graph(graph.id)
            self._sync_inspector()
        except Exception as exc:
            QMessageBox.warning(self, "Recompute graph", str(exc))

    def _apply_series_preset(self, preset: str) -> None:
        graph = self._current_graph()
        if graph is None:
            return
        rainbow = (
            (230, 25, 75, 255),
            (245, 130, 48, 255),
            (255, 225, 25, 255),
            (60, 180, 75, 255),
            (0, 130, 200, 255),
            (145, 30, 180, 255),
        )
        bw_lines = ("solid", "dash", "dot", "dash-dot")
        changed = []
        for index, series in enumerate(graph.series):
            if preset == "bw":
                style = replace(
                    series.style,
                    color=(0, 0, 0, 255),
                    line_style=bw_lines[index % len(bw_lines)],
                )
            else:
                colors = rainbow if preset == "rainbow" else PALETTE
                style = replace(series.style, color=colors[index % len(colors)])
            changed.append(replace(series, style=style))
        after = graph.replace_series(changed)
        self.undo_stack.push(GraphEditCommand(self, graph, after, False, "Apply series preset"))

    def _template_folder(self) -> Path:
        root = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation)
        folder = Path(root) / "templates"
        folder.mkdir(parents=True, exist_ok=True)
        return folder

    def _save_template(self) -> None:
        graph = self._current_graph()
        if graph is None:
            return
        name, ok = QInputDialog.getText(self, "Save template", "Template name:", text=graph.title)
        if not ok or not name.strip():
            return
        safe = "".join(char if char.isalnum() or char in "-_ " else "_" for char in name).strip()
        save_template(self._template_folder() / safe, graph, name.strip())

    def _choose_template(self, title: str) -> Path | None:
        templates = sorted(self._template_folder().glob("*.bernardyn-template.json"))
        if not templates:
            QMessageBox.information(self, title, "No saved templates are available.")
            return None
        labels = [path.stem.replace(".bernardyn-template", "") for path in templates]
        selected, ok = QInputDialog.getItem(self, title, "Template:", labels, 0, False)
        if not ok:
            return None
        return templates[labels.index(selected)]

    def _apply_template(self) -> None:
        graph = self._current_graph()
        path = self._choose_template("Apply template")
        if graph is None or path is None:
            return
        after = apply_template(graph, load_template(path))
        self.undo_stack.push(GraphEditCommand(self, graph, after, True, "Apply graph template"))

    def _delete_template(self) -> None:
        path = self._choose_template("Delete template")
        if path is not None and QMessageBox.question(self, "Delete template", f"Delete {path.name}?") == QMessageBox.StandardButton.Yes:
            path.unlink()

    def _restore_layout(self) -> None:
        if not self.controller.workspace.layout_state:
            self._reset_panel_layout()
            return
        try:
            state = json.loads(self.controller.workspace.layout_state)
            self.restoreState(base64.b64decode(state["window_state"]))
            self.restoreGeometry(base64.b64decode(state["geometry"]))
        except Exception:
            log.warning("could not restore saved window layout", exc_info=True)
        finally:
            # A floating dock may have been left on a disconnected display, or
            # hidden with its close button.  Its location is convenience state,
            # not workspace data, so never let it make the primary controls
            # disappear on the next launch.
            self._reset_panel_layout()

    def _confirm_discard(self) -> bool:
        if not self.controller.workspace.dirty:
            return True
        answer = QMessageBox.question(
            self,
            "Unsaved changes",
            "Save the current workspace before continuing?",
            QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
        )
        if answer == QMessageBox.StandardButton.Cancel:
            return False
        if answer == QMessageBox.StandardButton.Save:
            return self._save()
        return True

    def closeEvent(self, event: QCloseEvent) -> None:
        for worker in self._workers:
            worker.cancelled = True
        if self._confirm_discard():
            self._release_workspace_lock()
            event.accept()
        else:
            event.ignore()
