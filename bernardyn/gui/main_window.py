"""Controller-driven Bernardyn desktop workbench."""

from __future__ import annotations

import base64
import json
import logging
from dataclasses import replace
from pathlib import Path

from PySide6.QtCore import QObject, QRunnable, QStandardPaths, Qt, QThreadPool, Signal
from PySide6.QtGui import QAction, QCloseEvent, QKeySequence, QUndoCommand, QUndoStack
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDockWidget,
    QFileDialog,
    QInputDialog,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from bernardyn.core.controller import PALETTE, ApplicationController
from bernardyn.core.models import GraphDocument
from bernardyn.gui.dialogs import (
    GraphSelectionDialog,
    HDFMappingDialog,
    LocationDialog,
    SeriesTransformParameterDialog,
)
from bernardyn.gui.graph_page import GraphPage, PreviewPage
from bernardyn.gui.inspector import InspectorWidget
from bernardyn.io.container import load_package
from bernardyn.io.igor import export_datasets_to_h5xp
from bernardyn.renderers import builtin_renderers
from bernardyn.template.graph_templates import apply_template, load_template, save_template

log = logging.getLogger(__name__)

DATA_FILE_SUFFIXES = frozenset({".h5", ".hdf5", ".hdf", ".nxs", ".dat", ".txt", ".csv"})


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


class WorkerSignals(QObject):
    loaded = Signal(object, str)
    failed = Signal(str)
    finished = Signal(object)


class SourceLoadWorker(QRunnable):
    def __init__(self, controller, location, graph_id, q_unit, error_fraction) -> None:
        super().__init__()
        self.controller = controller
        self.location = location
        self.graph_id = graph_id
        self.q_unit = q_unit
        self.error_fraction = error_fraction
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
                self.signals.loaded.emit(record, self.graph_id)
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


class MainWindow(QMainWindow):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Bernardyn")
        self.resize(1500, 900)
        self.controller = ApplicationController()
        self.renderers = builtin_renderers()
        self.thread_pool = QThreadPool.globalInstance()
        self._workers: set[SourceLoadWorker] = set()
        self.undo_stack = QUndoStack(self)
        self.tabs = QTabWidget(self)
        self.tabs.setTabsClosable(True)
        self.tabs.currentChanged.connect(self._active_tab_changed)
        self.tabs.tabCloseRequested.connect(self._close_tab)
        self.setCentralWidget(self.tabs)
        self.dataset_list = QListWidget(self)
        self.dataset_list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.dataset_list.itemDoubleClicked.connect(lambda _: self._add_existing_dataset())
        self.inspector = InspectorWidget(self.controller.transforms, self)
        self.inspector.graphChanged.connect(self._queue_graph_change)
        self.inspector.transformRequested.connect(self._set_transform)
        self._build_docks()
        self._build_actions()
        self._build_menus()
        self.statusBar().showMessage("Ready")
        self._rebuild_tabs()

    def _build_docks(self) -> None:
        data_dock = QDockWidget("Data catalog", self)
        data_widget = QWidget(data_dock)
        layout = QVBoxLayout(data_widget)
        open_button = QPushButton("Open data…", data_widget)
        open_button.clicked.connect(self._open_data)
        open_folder_button = QPushButton("Open folder…", data_widget)
        open_folder_button.clicked.connect(self._open_folder)
        add_button = QPushButton("Add selected to graph", data_widget)
        add_button.clicked.connect(self._add_existing_dataset)
        remove_button = QPushButton("Remove selected", data_widget)
        remove_button.clicked.connect(self._remove_datasets)
        cancel_button = QPushButton("Cancel loading", data_widget)
        cancel_button.clicked.connect(self._cancel_loading)
        layout.addWidget(open_button)
        layout.addWidget(open_folder_button)
        layout.addWidget(self.dataset_list, 1)
        layout.addWidget(add_button)
        layout.addWidget(remove_button)
        layout.addWidget(cancel_button)
        data_dock.setWidget(data_widget)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, data_dock)

        inspector_dock = QDockWidget("Graph inspector", self)
        inspector_dock.setWidget(self.inspector)
        inspector_dock.setMinimumWidth(340)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, inspector_dock)

    def _action(self, text, slot, shortcut=None) -> QAction:
        action = QAction(text, self)
        action.triggered.connect(slot)
        if shortcut:
            action.setShortcut(shortcut)
        return action

    def _build_actions(self) -> None:
        self.new_workspace_action = self._action("New workspace", self._new_workspace, QKeySequence.StandardKey.New)
        self.open_data_action = self._action("Open data…", self._open_data, QKeySequence.StandardKey.Open)
        self.open_folder_action = self._action("Open folder…", self._open_folder, "Ctrl+Shift+O")
        self.workspace_properties_action = self._action(
            "Workspace properties…", self._workspace_properties
        )
        self.open_package_action = self._action("Open package…", self._open_package, "Ctrl+Shift+O")
        self.import_graph_action = self._action("Import graph from package…", self._import_graph)
        self.save_action = self._action("Save", self._save, QKeySequence.StandardKey.Save)
        self.save_as_action = self._action("Save workspace package as…", self._save_workspace_as, QKeySequence.StandardKey.SaveAs)
        self.save_graph_action = self._action("Save graph package…", self._save_graph)
        self.export_image_action = self._action("Export image…", self._export_image, "Ctrl+E")
        self.export_csv_action = self._action("Export displayed data as CSV…", self._export_csv)
        self.export_itx_action = self._action("Export displayed data as Igor ITX…", self._export_itx)
        self.export_h5xp_action = self._action("Export canonical data to Igor h5xp…", self._export_h5xp)
        self.copy_action = self._action("Copy graph", self._copy_graph, QKeySequence.StandardKey.Copy)
        self.new_2d_action = self._action("New 2D graph", lambda: self._new_graph("plot2d"))
        self.new_waterfall_action = self._action("New 3D waterfall", lambda: self._new_graph("opengl_waterfall"))
        self.new_surface_action = self._action("New 3D surface", lambda: self._new_graph("opengl_surface"))
        self.recompute_action = self._action("Recompute with current version", self._recompute_graph)
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

    def _build_menus(self) -> None:
        file_menu = self.menuBar().addMenu("&File")
        for action in (
            self.new_workspace_action, self.workspace_properties_action,
            self.open_data_action, self.open_folder_action, self.open_package_action,
            self.import_graph_action, None, self.save_action, self.save_as_action,
            self.save_graph_action, None, self.export_image_action, self.export_csv_action,
            self.export_itx_action, self.export_h5xp_action,
        ):
            file_menu.addSeparator() if action is None else file_menu.addAction(action)
        edit_menu = self.menuBar().addMenu("&Edit")
        edit_menu.addActions([self.undo_action, self.redo_action, self.copy_action])
        graph_menu = self.menuBar().addMenu("&Graph")
        graph_menu.addActions(
            [self.new_2d_action, self.new_waterfall_action, self.new_surface_action, self.recompute_action]
        )
        preset_menu = graph_menu.addMenu("Series presets")
        preset_menu.addActions(
            [self.color_preset_action, self.bw_preset_action, self.rainbow_preset_action]
        )
        template_menu = self.menuBar().addMenu("&Templates")
        template_menu.addActions(
            [self.save_template_action, self.apply_template_action, self.delete_template_action]
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

    def _new_workspace(self) -> None:
        if not self._confirm_discard():
            return
        self.controller.new_workspace()
        self.undo_stack.clear()
        self._rebuild_tabs()

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
        graph = self.controller.new_graph(renderer_id)
        page = GraphPage(graph, self, renderers=self.renderers)
        self.tabs.addTab(page, graph.title)
        self.tabs.setCurrentWidget(page)
        self._render_graph(graph.id)

    def _close_tab(self, index: int) -> None:
        page = self.tabs.widget(index)
        if not isinstance(page, GraphPage):
            self.tabs.removeTab(index)
            return
        self.controller.close_graph(page.graph_id)
        self.tabs.removeTab(index)
        page.deleteLater()
        if self.tabs.count() == 0:
            self._rebuild_tabs()

    def _active_tab_changed(self, index: int) -> None:
        page = self.tabs.widget(index)
        if isinstance(page, GraphPage):
            self.controller.workspace.active_graph_id = page.graph_id
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
        if page.fallback_reason:
            self.statusBar().showMessage(f"OpenGL unavailable; showing 2D fallback: {page.fallback_reason}")

    def _render_graph(self, graph_id: str) -> None:
        graph = self.controller.workspace.graph(graph_id)
        for index in range(self.tabs.count()):
            page = self.tabs.widget(index)
            if isinstance(page, GraphPage) and page.graph_id == graph_id:
                self._render_page(page, graph)
                self.tabs.setTabText(index, graph.title)
                return

    def _sync_inspector(self) -> None:
        graph = self._current_graph()
        warnings = self.controller.graph_warnings(graph.id) if graph else self.controller.warnings
        self.inspector.set_graph(
            graph,
            self.controller.workspace.datasets,
            warnings,
            read_only=bool(
                graph
                and graph.id
                in (self.controller.read_only_graphs | self.controller.preview_only_graphs)
            ),
        )

    def _queue_graph_change(self, graph: GraphDocument, recompute: bool, text: str) -> None:
        try:
            before = self.controller.workspace.graph(graph.id)
            self.undo_stack.push(GraphEditCommand(self, before, graph, recompute, text))
        except Exception as exc:
            QMessageBox.warning(self, "Graph change", str(exc))
            self._sync_inspector()

    def _commit_graph(self, graph: GraphDocument, recompute: bool) -> None:
        self.controller.update_graph(graph, recompute=recompute)
        self._render_graph(graph.id)
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
            series=series,
            x_axis=replace(graph.x_axis, label=transform.default_x_label, log=transform.default_x_log, auto_range=True),
            y_axis=replace(graph.y_axis, label=transform.default_y_label, log=transform.default_y_log, auto_range=True),
        )
        self.undo_stack.push(GraphEditCommand(self, before, after, True, f"Set {transform.name} view"))

    def _open_data(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Open scattering data",
            "",
            "Scattering data (*.h5 *.hdf5 *.hdf *.nxs *.dat *.txt *.csv);;All files (*)",
        )
        if not paths:
            return
        self._open_data_paths([Path(value) for value in paths])

    @staticmethod
    def _folder_data_files(folder: Path) -> list[Path]:
        """Return supported source files beneath *folder*, excluding Bernardyn packages."""
        return sorted(
            (
                path
                for path in folder.rglob("*")
                if path.is_file()
                and path.suffix.lower() in DATA_FILE_SUFFIXES
                and not path.name.lower().endswith(".bernardyn.h5")
            ),
            key=lambda path: str(path).lower(),
        )

    def _open_folder(self) -> None:
        selected = QFileDialog.getExistingDirectory(self, "Open folder containing scattering data")
        if not selected:
            return
        paths = self._folder_data_files(Path(selected))
        if not paths:
            QMessageBox.information(
                self,
                "Open folder",
                "No supported HDF5/NXcanSAS or text data files were found in this folder.",
            )
            return
        if len(paths) > 20:
            answer = QMessageBox.question(
                self,
                "Open folder",
                f"Found {len(paths)} supported data files. Load all of them?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
        self._open_data_paths(paths)

    def _open_data_paths(self, paths: list[Path]) -> None:
        graph = self._current_graph()
        if graph is None:
            return
        started_workers = False
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
            if len(locations) > 1:
                dialog = LocationDialog(locations, self)
                if dialog.exec() != dialog.DialogCode.Accepted:
                    continue
                locations = dialog.selected()
            q_unit = "1/A"
            error_fraction = 0.05
            if path.suffix.lower() in (".dat", ".txt", ".csv"):
                q_unit, ok = QInputDialog.getItem(
                    self, "Text data Q unit", f"Q unit for {path.name}:",
                    ["1/A", "1/nm", "1/pm", "1/um", "1/mm"], 0, False,
                )
                if not ok:
                    continue
                error_percent, ok = QInputDialog.getDouble(
                    self,
                    "Missing text uncertainty",
                    "Synthesized intensity uncertainty (%):",
                    5.0,
                    0.0001,
                    100.0,
                    3,
                )
                if not ok:
                    continue
                error_fraction = error_percent / 100.0
            for location in locations:
                worker = SourceLoadWorker(
                    self.controller, location, graph.id, q_unit, error_fraction
                )
                worker.signals.loaded.connect(self._source_loaded)
                worker.signals.failed.connect(lambda message: QMessageBox.warning(self, "Load error", message))
                worker.signals.finished.connect(self._worker_finished)
                self._workers.add(worker)
                self.thread_pool.start(worker)
                started_workers = True
        if started_workers:
            self.statusBar().showMessage("Loading data…")

    def _source_loaded(self, record, graph_id: str) -> None:
        try:
            if not any(graph.id == graph_id for graph in self.controller.workspace.graphs):
                graph_id = self.controller.workspace.active_graph_id
            dataset = record.to_dataset()
            self.controller.add_dataset(dataset, graph_id=graph_id)
            self._refresh_dataset_list()
            self._render_graph(graph_id)
            self._sync_inspector()
            self.statusBar().showMessage(f"Loaded {dataset.label}", 5000)
        except Exception as exc:
            QMessageBox.warning(self, "Load error", str(exc))

    def _worker_finished(self, worker) -> None:
        self._workers.discard(worker)
        if not self._workers:
            self.statusBar().showMessage("Ready", 2000)

    def _cancel_loading(self) -> None:
        for worker in self._workers:
            worker.cancelled = True
        self.statusBar().showMessage("Cancelling data loads…", 3000)

    def _refresh_dataset_list(self) -> None:
        selected = {item.data(Qt.ItemDataRole.UserRole) for item in self.dataset_list.selectedItems()}
        self.dataset_list.clear()
        for dataset in self.controller.workspace.datasets.values():
            item = QListWidgetItem(f"{dataset.label}  ({len(dataset.q):,} points)")
            item.setData(Qt.ItemDataRole.UserRole, dataset.id)
            self.dataset_list.addItem(item)
            if dataset.id in selected:
                item.setSelected(True)

    def _add_existing_dataset(self) -> None:
        graph = self._current_graph()
        if graph is None:
            return
        for item in self.dataset_list.selectedItems():
            dataset = self.controller.workspace.datasets[item.data(Qt.ItemDataRole.UserRole)]
            self.controller.add_dataset(dataset, graph_id=graph.id)
        self._render_graph(graph.id)
        self._sync_inspector()

    def _remove_datasets(self) -> None:
        ids = {item.data(Qt.ItemDataRole.UserRole) for item in self.dataset_list.selectedItems()}
        if not ids:
            return
        references = sum(
            1 for graph in self.controller.workspace.graphs for series in graph.series if series.dataset_id in ids
        )
        if references and QMessageBox.question(
            self, "Remove datasets", f"Remove {len(ids)} dataset(s) and {references} graph reference(s)?"
        ) != QMessageBox.StandardButton.Yes:
            return
        for graph in tuple(self.controller.workspace.graphs):
            retained = tuple(series for series in graph.series if series.dataset_id not in ids)
            if retained != graph.series:
                self.controller.update_graph(replace(graph, series=retained), recompute=True)
        for dataset_id in ids:
            self.controller.workspace.datasets.pop(dataset_id, None)
        self.controller.workspace.dirty = True
        self._refresh_dataset_list()
        for graph in self.controller.workspace.graphs:
            self._render_graph(graph.id)
        self._sync_inspector()

    def _open_package(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Open Bernardyn package", "", "Bernardyn (*.bernardyn.h5);;HDF5 (*.h5)")
        if not path or not self._confirm_discard():
            return
        try:
            loaded = self.controller.open_package(path)
            self.undo_stack.clear()
            self._rebuild_tabs()
            if loaded.warnings:
                QMessageBox.warning(self, "Package warnings", "\n".join(loaded.warnings))
            self._restore_layout()
        except Exception as exc:
            QMessageBox.critical(self, "Open package", str(exc))

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
        path, _ = QFileDialog.getSaveFileName(self, "Save workspace package", "workspace.bernardyn.h5", "Bernardyn (*.bernardyn.h5)")
        return bool(path) and self._save_to(path)

    def _save_graph(self) -> bool:
        graph = self._current_graph()
        if graph is None:
            return False
        path, _ = QFileDialog.getSaveFileName(self, "Save graph package", f"{graph.title}.bernardyn.h5", "Bernardyn (*.bernardyn.h5)")
        return bool(path) and self._save_to(path, graph_ids=[graph.id])

    def _save_to(self, path, graph_ids=None) -> bool:
        try:
            previews, renderer_data = self._collect_artifacts()
            saved = self.controller.save(
                path, graph_ids=graph_ids, previews=previews, renderer_data=renderer_data
            )
            self.statusBar().showMessage(f"Saved {saved.name}", 5000)
            return True
        except Exception as exc:
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
            return
        try:
            state = json.loads(self.controller.workspace.layout_state)
            self.restoreState(base64.b64decode(state["window_state"]))
            self.restoreGeometry(base64.b64decode(state["geometry"]))
        except Exception:
            log.warning("could not restore saved window layout", exc_info=True)

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
            event.accept()
        else:
            event.ignore()
