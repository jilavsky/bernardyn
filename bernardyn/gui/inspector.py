"""Graph inspector that edits GraphDocument values, never renderer objects."""

from __future__ import annotations

from dataclasses import replace
from typing import Mapping

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDoubleSpinBox,
    QFontComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from bernardyn.core.models import Dataset, GraphDocument, SeriesView
from bernardyn.core.transforms import TransformRegistry
from bernardyn.gui.dialogs import AnnotationDialog


class InspectorWidget(QScrollArea):
    graphChanged = Signal(object, bool, str)
    transformRequested = Signal(str)

    def __init__(self, transforms: TransformRegistry, parent=None) -> None:
        super().__init__(parent)
        self.transforms = transforms
        self._graph: GraphDocument | None = None
        self._datasets: Mapping[str, Dataset] = {}
        self._syncing = False
        self.setWidgetResizable(True)
        content = QWidget(self)
        self.setWidget(content)
        layout = QVBoxLayout(content)
        layout.addWidget(self._build_graph_group())
        layout.addWidget(self._build_3d_group())
        layout.addWidget(self._build_series_group())
        layout.addWidget(self._build_annotation_group())
        self.warning = QLabel(self)
        self.warning.setWordWrap(True)
        self.warning.setStyleSheet("color: #9a6700")
        layout.addWidget(self.warning)
        layout.addStretch(1)

    def _build_graph_group(self) -> QGroupBox:
        group = QGroupBox("Graph", self)
        form = QFormLayout(group)
        self.title = QLineEdit(group)
        self.title.editingFinished.connect(self._edit_graph_text)
        self.description = QLineEdit(group)
        self.notes = QLineEdit(group)
        self.description.editingFinished.connect(self._edit_graph_text)
        self.notes.editingFinished.connect(self._edit_graph_text)
        self.renderer = QComboBox(group)
        self.renderer.addItem("2D plot", "plot2d")
        self.renderer.addItem("3D waterfall", "opengl_waterfall")
        self.renderer.addItem("3D surface", "opengl_surface")
        self.renderer.currentIndexChanged.connect(self._edit_renderer)
        self.transform = QComboBox(group)
        for item in self.transforms:
            self.transform.addItem(item.name, item.id)
        self.transform.currentIndexChanged.connect(self._request_transform)
        self.x_label = QLineEdit(group)
        self.y_label = QLineEdit(group)
        self.x_label.editingFinished.connect(self._edit_graph_text)
        self.y_label.editingFinished.connect(self._edit_graph_text)
        self.x_log = QCheckBox("Log X", group)
        self.y_log = QCheckBox("Log Y", group)
        self.x_log.toggled.connect(self._edit_axes)
        self.y_log.toggled.connect(self._edit_axes)
        log_row = QWidget(group)
        log_layout = QHBoxLayout(log_row)
        log_layout.setContentsMargins(0, 0, 0, 0)
        log_layout.addWidget(self.x_log)
        log_layout.addWidget(self.y_log)
        self.x_auto = QCheckBox("Auto X", group)
        self.y_auto = QCheckBox("Auto Y", group)
        self.x_auto.toggled.connect(self._edit_axes)
        self.y_auto.toggled.connect(self._edit_axes)
        auto_row = QWidget(group)
        auto_layout = QHBoxLayout(auto_row)
        auto_layout.setContentsMargins(0, 0, 0, 0)
        auto_layout.addWidget(self.x_auto)
        auto_layout.addWidget(self.y_auto)
        self.axis_x_min = QLineEdit(group)
        self.axis_x_max = QLineEdit(group)
        self.axis_y_min = QLineEdit(group)
        self.axis_y_max = QLineEdit(group)
        for field in (
            self.axis_x_min,
            self.axis_x_max,
            self.axis_y_min,
            self.axis_y_max,
        ):
            field.setPlaceholderText("automatic")
            field.editingFinished.connect(self._edit_axes)
        self.x_grid = QCheckBox("X grid", group)
        self.y_grid = QCheckBox("Y grid", group)
        self.x_grid.toggled.connect(self._edit_axes)
        self.y_grid.toggled.connect(self._edit_axes)
        grid_row = QWidget(group)
        grid_layout = QHBoxLayout(grid_row)
        grid_layout.setContentsMargins(0, 0, 0, 0)
        grid_layout.addWidget(self.x_grid)
        grid_layout.addWidget(self.y_grid)
        self.axis_thickness = self._double(0.1, 10, 1)
        self.axis_thickness.editingFinished.connect(self._edit_axes)
        self.axis_color = QPushButton("Choose…", group)
        self.axis_color.clicked.connect(self._choose_axis_color)
        self.legend = QCheckBox("Show legend", group)
        self.legend.toggled.connect(self._edit_legend)
        self.legend_position = QComboBox(group)
        for label, value in (
            ("Top right", "top-right"),
            ("Top left", "top-left"),
            ("Bottom right", "bottom-right"),
            ("Bottom left", "bottom-left"),
        ):
            self.legend_position.addItem(label, value)
        self.legend_position.currentIndexChanged.connect(self._edit_legend)
        self.legend_frame = QCheckBox("Frame", group)
        self.legend_frame.toggled.connect(self._edit_legend)
        self.legend_columns = QSpinBox(group)
        self.legend_columns.setRange(1, 8)
        self.legend_columns.editingFinished.connect(self._edit_legend)
        self.font_family = QFontComboBox(group)
        self.font_family.currentFontChanged.connect(self._edit_typography)
        self.title_font_size = QSpinBox(group)
        self.font_size = QSpinBox(group)
        self.tick_font_size = QSpinBox(group)
        self.legend_font_size = QSpinBox(group)
        for control in (
            self.title_font_size,
            self.font_size,
            self.tick_font_size,
            self.legend_font_size,
        ):
            control.setRange(6, 144)
            control.editingFinished.connect(self._edit_typography)
        self.canvas_width = QSpinBox(group)
        self.canvas_height = QSpinBox(group)
        for control, value in ((self.canvas_width, 1950), (self.canvas_height, 1350)):
            control.setRange(100, 16384)
            control.setValue(value)
            control.editingFinished.connect(self._edit_dimensions)
        self.width_in = self._double(0.1, 200, 6.5)
        self.height_in = self._double(0.1, 200, 4.5)
        self.dpi = QSpinBox(group)
        self.dpi.setRange(36, 2400)
        self.dpi.setValue(300)
        for control in (self.width_in, self.height_in, self.dpi):
            control.editingFinished.connect(self._edit_dimensions)
        self.background = QPushButton("Choose…", group)
        self.background.clicked.connect(self._choose_background)
        form.addRow("Title:", self.title)
        form.addRow("Description:", self.description)
        form.addRow("Notes:", self.notes)
        form.addRow("Renderer:", self.renderer)
        form.addRow("Plot view:", self.transform)
        form.addRow("X label:", self.x_label)
        form.addRow("Y label:", self.y_label)
        form.addRow("Axes:", log_row)
        form.addRow("Ranges:", auto_row)
        form.addRow("X minimum:", self.axis_x_min)
        form.addRow("X maximum:", self.axis_x_max)
        form.addRow("Y minimum:", self.axis_y_min)
        form.addRow("Y maximum:", self.axis_y_max)
        form.addRow("Grid:", grid_row)
        form.addRow("Axis thickness:", self.axis_thickness)
        form.addRow("Axis color:", self.axis_color)
        form.addRow("Legend:", self.legend)
        form.addRow("Legend position:", self.legend_position)
        form.addRow("Legend frame:", self.legend_frame)
        form.addRow("Legend columns:", self.legend_columns)
        form.addRow("Font family:", self.font_family)
        form.addRow("Title font size:", self.title_font_size)
        form.addRow("Axis-label font size:", self.font_size)
        form.addRow("Tick font size:", self.tick_font_size)
        form.addRow("Legend font size:", self.legend_font_size)
        form.addRow("Canvas width (px):", self.canvas_width)
        form.addRow("Canvas height (px):", self.canvas_height)
        form.addRow("Output width (in):", self.width_in)
        form.addRow("Output height (in):", self.height_in)
        form.addRow("Output DPI:", self.dpi)
        form.addRow("Background:", self.background)
        return group

    def _build_3d_group(self) -> QGroupBox:
        group = QGroupBox("3D view", self)
        self.opengl_group = group
        form = QFormLayout(group)
        self.spacing_3d = self._double(0.001, 1e6, 1.0)
        self.spacing_3d.setDecimals(4)
        self.normalization_3d = QComboBox(group)
        for label, value in (("None", "none"), ("Maximum", "maximum"), ("Area", "area")):
            self.normalization_3d.addItem(label, value)
        self.surface_samples = QSpinBox(group)
        self.surface_samples.setRange(16, 4096)
        self.surface_samples.setValue(512)
        self.series_axis_key = QLineEdit(group)
        self.series_axis_key.setPlaceholderText("blank uses graph order")
        self.projection_3d = QComboBox(group)
        self.projection_3d.addItem("Perspective", "perspective")
        self.projection_3d.addItem("Orthographic", "orthographic")
        self.show_grid_3d = QCheckBox("Show axes and grid", group)
        self.camera_distance = self._double(0.1, 1e7, 40.0)
        self.camera_elevation = self._double(-90, 90, 25.0)
        self.camera_azimuth = self._double(-360, 360, -45.0)
        for control in (
            self.spacing_3d,
            self.surface_samples,
            self.series_axis_key,
            self.camera_distance,
            self.camera_elevation,
            self.camera_azimuth,
        ):
            control.editingFinished.connect(self._edit_3d)
        self.normalization_3d.currentIndexChanged.connect(self._edit_3d)
        self.projection_3d.currentIndexChanged.connect(self._edit_3d)
        self.show_grid_3d.toggled.connect(self._edit_3d)
        form.addRow("Dataset spacing:", self.spacing_3d)
        form.addRow("Normalization:", self.normalization_3d)
        form.addRow("Surface Q samples:", self.surface_samples)
        form.addRow("Series metadata key:", self.series_axis_key)
        form.addRow("Projection:", self.projection_3d)
        form.addRow("Grid:", self.show_grid_3d)
        form.addRow("Camera distance:", self.camera_distance)
        form.addRow("Camera elevation:", self.camera_elevation)
        form.addRow("Camera azimuth:", self.camera_azimuth)
        return group

    def _build_series_group(self) -> QGroupBox:
        group = QGroupBox("Datasets in graph", self)
        layout = QVBoxLayout(group)
        self.series_list = QListWidget(group)
        self.series_list.currentItemChanged.connect(self._series_selected)
        self.series_list.itemChanged.connect(self._series_visibility)
        layout.addWidget(self.series_list)
        row = QHBoxLayout()
        for text, callback in (
            ("Up", lambda: self._move_series(-1)),
            ("Down", lambda: self._move_series(1)),
            ("Remove", self._remove_series),
        ):
            button = QPushButton(text, group)
            button.clicked.connect(callback)
            row.addWidget(button)
        layout.addLayout(row)
        form = QFormLayout()
        self.series_label = QLineEdit(group)
        self.series_label.editingFinished.connect(self._edit_series_label)
        self.color = QPushButton("Choose…", group)
        self.color.clicked.connect(self._choose_color)
        self.line_style = QComboBox(group)
        for value in ("solid", "dash", "dot", "dash-dot", "none"):
            self.line_style.addItem(value.title(), value)
        self.line_style.currentIndexChanged.connect(self._edit_style)
        self.line_width = self._double(0, 20, 1.5)
        self.line_width.editingFinished.connect(self._edit_style)
        self.symbol = QComboBox(group)
        for label, value in (
            ("Circle", "o"), ("Square", "s"), ("Triangle", "t"),
            ("Diamond", "d"), ("Plus", "+"), ("None", "none"),
        ):
            self.symbol.addItem(label, value)
        self.symbol.currentIndexChanged.connect(self._edit_style)
        self.symbol_size = self._double(0, 50, 6)
        self.symbol_size.editingFinished.connect(self._edit_style)
        self.opacity = self._double(0, 1, 1)
        self.opacity.setSingleStep(0.1)
        self.opacity.editingFinished.connect(self._edit_style)
        self.error_bars = QCheckBox("Visible", group)
        self.error_bars.toggled.connect(self._edit_style)
        self.error_color = QPushButton("Choose…", group)
        self.error_color.clicked.connect(self._choose_error_color)
        self.error_width = self._double(0, 20, 1)
        self.error_width.editingFinished.connect(self._edit_style)
        self.multiplier = self._double(-1e12, 1e12, 1)
        self.multiplier.setDecimals(8)
        self.multiplier.editingFinished.connect(self._edit_series_transform)
        self.offset = self._double(-1e12, 1e12, 0)
        self.offset.setDecimals(8)
        self.offset.editingFinished.connect(self._edit_series_transform)
        self.q_min = QLineEdit(group)
        self.q_max = QLineEdit(group)
        self.q_min.setPlaceholderText("automatic")
        self.q_max.setPlaceholderText("automatic")
        self.q_min.editingFinished.connect(self._edit_series_transform)
        self.q_max.editingFinished.connect(self._edit_series_transform)
        form.addRow("Legend label:", self.series_label)
        form.addRow("Color:", self.color)
        form.addRow("Line:", self.line_style)
        form.addRow("Line width:", self.line_width)
        form.addRow("Symbol:", self.symbol)
        form.addRow("Symbol size:", self.symbol_size)
        form.addRow("Opacity:", self.opacity)
        form.addRow("Error bars:", self.error_bars)
        form.addRow("Error color:", self.error_color)
        form.addRow("Error width:", self.error_width)
        form.addRow("Multiplier:", self.multiplier)
        form.addRow("Offset:", self.offset)
        form.addRow("Q minimum:", self.q_min)
        form.addRow("Q maximum:", self.q_max)
        layout.addLayout(form)
        self.series_controls = [
            self.series_label, self.color, self.line_style, self.line_width, self.symbol,
            self.symbol_size, self.opacity, self.error_bars, self.multiplier, self.offset,
            self.error_color, self.error_width, self.q_min, self.q_max,
        ]
        return group

    def _build_annotation_group(self) -> QGroupBox:
        group = QGroupBox("Annotations", self)
        layout = QVBoxLayout(group)
        self.annotations = QListWidget(group)
        self.annotations.itemDoubleClicked.connect(lambda _: self._edit_annotation())
        layout.addWidget(self.annotations)
        row = QHBoxLayout()
        for text, callback in (
            ("Add", self._add_annotation),
            ("Edit", self._edit_annotation),
            ("Delete", self._delete_annotation),
        ):
            button = QPushButton(text, group)
            button.clicked.connect(callback)
            row.addWidget(button)
        layout.addLayout(row)
        return group

    @staticmethod
    def _double(minimum: float, maximum: float, value: float) -> QDoubleSpinBox:
        spin = QDoubleSpinBox()
        spin.setRange(minimum, maximum)
        spin.setDecimals(3)
        spin.setValue(value)
        return spin

    def set_graph(
        self,
        graph: GraphDocument | None,
        datasets: Mapping[str, Dataset],
        warnings: list[str] | None = None,
        *,
        read_only: bool = False,
    ) -> None:
        self._syncing = True
        self._graph = graph
        self._datasets = datasets
        self.setEnabled(graph is not None and not read_only)
        self.warning.setText("\n".join(warnings or ([] if not read_only else ["Read-only archival graph"])))
        if graph is None:
            self.series_list.clear()
            self.annotations.clear()
            self._syncing = False
            return
        self.title.setText(graph.title)
        self.description.setText(graph.description)
        self.notes.setText(graph.notes)
        self.renderer.setCurrentIndex(max(0, self.renderer.findData(graph.renderer_id)))
        transform_id = graph.series[0].transform_id if graph.series else "raw"
        self.transform.setCurrentIndex(max(0, self.transform.findData(transform_id)))
        self.x_label.setText(graph.x_axis.label)
        self.y_label.setText(graph.y_axis.label)
        self.x_log.setChecked(graph.x_axis.log)
        self.y_log.setChecked(graph.y_axis.log)
        self.x_auto.setChecked(graph.x_axis.auto_range)
        self.y_auto.setChecked(graph.y_axis.auto_range)
        self.axis_x_min.setText(
            "" if graph.x_axis.minimum is None else f"{graph.x_axis.minimum:g}"
        )
        self.axis_x_max.setText(
            "" if graph.x_axis.maximum is None else f"{graph.x_axis.maximum:g}"
        )
        self.axis_y_min.setText(
            "" if graph.y_axis.minimum is None else f"{graph.y_axis.minimum:g}"
        )
        self.axis_y_max.setText(
            "" if graph.y_axis.maximum is None else f"{graph.y_axis.maximum:g}"
        )
        self.x_grid.setChecked(graph.x_axis.grid_major)
        self.y_grid.setChecked(graph.y_axis.grid_major)
        self.axis_thickness.setValue(graph.x_axis.thickness)
        self.axis_color.setStyleSheet(
            f"background: rgba({graph.x_axis.color[0]}, {graph.x_axis.color[1]}, "
            f"{graph.x_axis.color[2]}, {graph.x_axis.color[3]})"
        )
        self.legend.setChecked(graph.legend.visible)
        self.legend_position.setCurrentIndex(
            max(0, self.legend_position.findData(graph.legend.position))
        )
        self.legend_frame.setChecked(graph.legend.framed)
        self.legend_columns.setValue(graph.legend.columns)
        self.font_family.setCurrentFont(QFont(graph.typography.family))
        self.title_font_size.setValue(graph.typography.title_size)
        self.font_size.setValue(graph.typography.axis_label_size)
        self.tick_font_size.setValue(graph.typography.tick_size)
        self.legend_font_size.setValue(graph.typography.legend_size)
        self.canvas_width.setValue(graph.width_px)
        self.canvas_height.setValue(graph.height_px)
        self.width_in.setValue(graph.width_in)
        self.height_in.setValue(graph.height_in)
        self.dpi.setValue(graph.dpi)
        self.background.setStyleSheet(
            f"background: rgba({graph.background[0]}, {graph.background[1]}, "
            f"{graph.background[2]}, {graph.background[3]})"
        )
        config = graph.renderer_config
        self.opengl_group.setVisible(graph.renderer_id.startswith("opengl"))
        self.spacing_3d.setValue(float(config.get("spacing", 1.0)))
        self.normalization_3d.setCurrentIndex(
            max(0, self.normalization_3d.findData(config.get("normalization", "none")))
        )
        self.surface_samples.setValue(int(config.get("surface_samples", 512)))
        self.series_axis_key.setText(str(config.get("series_axis_key", "")))
        self.projection_3d.setCurrentIndex(
            max(0, self.projection_3d.findData(config.get("projection", "perspective")))
        )
        self.show_grid_3d.setChecked(bool(config.get("show_grid", True)))
        camera = config.get("camera", {})
        self.camera_distance.setValue(float(camera.get("distance", 40.0)))
        self.camera_elevation.setValue(float(camera.get("elevation", 25.0)))
        self.camera_azimuth.setValue(float(camera.get("azimuth", -45.0)))
        selected_id = self.current_series_id()
        self.series_list.clear()
        for series in graph.series:
            label = series.legend_label or datasets[series.dataset_id].label
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, series.id)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked if series.visible else Qt.CheckState.Unchecked)
            self.series_list.addItem(item)
            if series.id == selected_id:
                self.series_list.setCurrentItem(item)
        if self.series_list.currentItem() is None and self.series_list.count():
            self.series_list.setCurrentRow(0)
        self.annotations.clear()
        for annotation in graph.annotations:
            label = annotation.text or annotation.kind.value.replace("_", " ")
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, annotation.id)
            self.annotations.addItem(item)
        self._sync_series_controls()
        self._syncing = False

    def current_series_id(self) -> str | None:
        item = self.series_list.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def _series(self) -> SeriesView | None:
        series_id = self.current_series_id()
        if self._graph is None or series_id is None:
            return None
        return next((item for item in self._graph.series if item.id == series_id), None)

    def _replace_series(self, replacement: SeriesView, *, recompute: bool, text: str) -> None:
        if self._graph is None:
            return
        graph = self._graph.replace_series(
            replacement if item.id == replacement.id else item for item in self._graph.series
        )
        self._graph = graph
        self.graphChanged.emit(graph, recompute, text)

    def _edit_graph_text(self) -> None:
        if self._syncing or self._graph is None:
            return
        graph = replace(
            self._graph,
            title=self.title.text(),
            description=self.description.text(),
            notes=self.notes.text(),
            x_axis=replace(self._graph.x_axis, label=self.x_label.text()),
            y_axis=replace(self._graph.y_axis, label=self.y_label.text()),
        )
        self._graph = graph
        self.graphChanged.emit(graph, False, "Edit graph labels")

    def _edit_renderer(self) -> None:
        if self._syncing or self._graph is None:
            return
        renderer_id = self.renderer.currentData()
        config = dict(self._graph.renderer_config)
        config["renderer_version"] = "1.0"
        if renderer_id.startswith("opengl"):
            config.setdefault("spacing", 1.0)
            config.setdefault("normalization", "none")
            config.setdefault("surface_samples", 512)
            config.setdefault("camera", {"distance": 40, "elevation": 25, "azimuth": -45})
            config.setdefault("projection", "perspective")
            config.setdefault("show_grid", True)
            config["mode"] = "surface" if renderer_id == "opengl_surface" else "waterfall"
        graph = replace(self._graph, renderer_id=renderer_id, renderer_config=config)
        self._graph = graph
        self.opengl_group.setVisible(renderer_id.startswith("opengl"))
        self.graphChanged.emit(graph, False, "Change renderer")

    def _edit_3d(self) -> None:
        if self._syncing or self._graph is None:
            return
        key = self.series_axis_key.text().strip()
        positions: dict[str, float] = {}
        if key:
            for index, view in enumerate(self._graph.series):
                value = self._datasets[view.dataset_id].metadata.get(key, index)
                try:
                    positions[view.id] = float(value)
                except (TypeError, ValueError):
                    positions[view.id] = float(index)
        config = {
            **self._graph.renderer_config,
            "spacing": self.spacing_3d.value(),
            "normalization": self.normalization_3d.currentData(),
            "surface_samples": self.surface_samples.value(),
            "series_axis_key": key,
            "series_positions": positions,
            "projection": self.projection_3d.currentData(),
            "show_grid": self.show_grid_3d.isChecked(),
            "camera": {
                "distance": self.camera_distance.value(),
                "elevation": self.camera_elevation.value(),
                "azimuth": self.camera_azimuth.value(),
            },
        }
        graph = replace(self._graph, renderer_config=config)
        self._graph = graph
        self.graphChanged.emit(graph, False, "Change 3D view")

    def _request_transform(self) -> None:
        if not self._syncing:
            self.transformRequested.emit(self.transform.currentData())

    def _edit_axes(self) -> None:
        if self._syncing or self._graph is None:
            return
        try:
            x_axis = replace(
                self._graph.x_axis,
                log=self.x_log.isChecked(),
                minimum=self._optional_float(self.axis_x_min),
                maximum=self._optional_float(self.axis_x_max),
                auto_range=self.x_auto.isChecked(),
                grid_major=self.x_grid.isChecked(),
                thickness=self.axis_thickness.value(),
            )
            y_axis = replace(
                self._graph.y_axis,
                log=self.y_log.isChecked(),
                minimum=self._optional_float(self.axis_y_min),
                maximum=self._optional_float(self.axis_y_max),
                auto_range=self.y_auto.isChecked(),
                grid_major=self.y_grid.isChecked(),
                thickness=self.axis_thickness.value(),
            )
            graph = replace(self._graph, x_axis=x_axis, y_axis=y_axis)
        except ValueError:
            self.set_graph(self._graph, self._datasets)
            return
        self._graph = graph
        self.graphChanged.emit(graph, True, "Change axis scale")

    def _edit_legend(self) -> None:
        if self._syncing or self._graph is None:
            return
        graph = replace(
            self._graph,
            legend=replace(
                self._graph.legend,
                visible=self.legend.isChecked(),
                position=self.legend_position.currentData(),
                framed=self.legend_frame.isChecked(),
                columns=self.legend_columns.value(),
            ),
        )
        self._graph = graph
        self.graphChanged.emit(graph, False, "Change legend")

    def _edit_typography(self) -> None:
        if self._syncing or self._graph is None:
            return
        graph = replace(
            self._graph,
            typography=replace(
                self._graph.typography,
                family=self.font_family.currentFont().family(),
                title_size=self.title_font_size.value(),
                axis_label_size=self.font_size.value(),
                tick_size=self.tick_font_size.value(),
                legend_size=self.legend_font_size.value(),
            ),
        )
        self._graph = graph
        self.graphChanged.emit(graph, False, "Change typography")

    def _edit_dimensions(self) -> None:
        if self._syncing or self._graph is None:
            return
        if self.sender() in (self.width_in, self.height_in, self.dpi):
            width_in = self.width_in.value()
            height_in = self.height_in.value()
            dpi = self.dpi.value()
            width_px = round(width_in * dpi)
            height_px = round(height_in * dpi)
        else:
            width_px = self.canvas_width.value()
            height_px = self.canvas_height.value()
            dpi = self.dpi.value()
            width_in = width_px / dpi
            height_in = height_px / dpi
        graph = replace(
            self._graph,
            width_px=width_px,
            height_px=height_px,
            width_in=width_in,
            height_in=height_in,
            dpi=dpi,
        )
        self._graph = graph
        self.graphChanged.emit(graph, False, "Change canvas dimensions")

    def _choose_background(self) -> None:
        if self._graph is None:
            return
        selected = QColorDialog.getColor(
            QColor(*self._graph.background),
            self,
            "Graph background",
            QColorDialog.ColorDialogOption.ShowAlphaChannel,
        )
        if not selected.isValid():
            return
        color = (selected.red(), selected.green(), selected.blue(), selected.alpha())
        graph = replace(self._graph, background=color)
        self._graph = graph
        self.graphChanged.emit(graph, False, "Change graph background")

    def _choose_axis_color(self) -> None:
        if self._graph is None:
            return
        selected = QColorDialog.getColor(
            QColor(*self._graph.x_axis.color),
            self,
            "Axis color",
            QColorDialog.ColorDialogOption.ShowAlphaChannel,
        )
        if not selected.isValid():
            return
        color = (selected.red(), selected.green(), selected.blue(), selected.alpha())
        graph = replace(
            self._graph,
            x_axis=replace(self._graph.x_axis, color=color),
            y_axis=replace(self._graph.y_axis, color=color),
        )
        self._graph = graph
        self.graphChanged.emit(graph, False, "Change axis color")

    def _series_selected(self) -> None:
        if not self._syncing:
            self._sync_series_controls()

    def _sync_series_controls(self) -> None:
        series = self._series()
        for control in getattr(self, "series_controls", []):
            control.setEnabled(series is not None)
        if series is None:
            return
        self._syncing = True
        style = series.style
        self.series_label.setText(series.legend_label or "")
        self.color.setStyleSheet(
            f"background: rgba({style.color[0]}, {style.color[1]}, {style.color[2]}, {style.color[3]})"
        )
        self.line_style.setCurrentIndex(max(0, self.line_style.findData(style.line_style)))
        self.line_width.setValue(style.line_width)
        self.symbol.setCurrentIndex(max(0, self.symbol.findData(style.symbol or "none")))
        self.symbol_size.setValue(style.symbol_size)
        self.opacity.setValue(style.opacity)
        self.error_bars.setChecked(style.show_error_bars)
        self.error_color.setStyleSheet(
            f"background: rgba({style.error_color[0]}, {style.error_color[1]}, "
            f"{style.error_color[2]}, {style.error_color[3]})"
        )
        self.error_width.setValue(style.error_width)
        self.multiplier.setValue(series.multiplier)
        self.offset.setValue(series.offset)
        self.q_min.setText("" if series.q_range[0] is None else f"{series.q_range[0]:g}")
        self.q_max.setText("" if series.q_range[1] is None else f"{series.q_range[1]:g}")
        self._syncing = False

    def _series_visibility(self, item: QListWidgetItem) -> None:
        if self._syncing or self._graph is None:
            return
        series_id = item.data(Qt.ItemDataRole.UserRole)
        series = next(value for value in self._graph.series if value.id == series_id)
        self._replace_series(
            replace(series, visible=item.checkState() == Qt.CheckState.Checked),
            recompute=False,
            text="Toggle dataset visibility",
        )

    def _edit_series_label(self) -> None:
        if self._syncing or (series := self._series()) is None:
            return
        self._replace_series(
            replace(series, legend_label=self.series_label.text()),
            recompute=False,
            text="Rename dataset",
        )

    def _choose_color(self) -> None:
        series = self._series()
        if series is None:
            return
        initial = QColor(*series.style.color)
        selected = QColorDialog.getColor(initial, self, "Dataset color", QColorDialog.ColorDialogOption.ShowAlphaChannel)
        if not selected.isValid():
            return
        color = (selected.red(), selected.green(), selected.blue(), selected.alpha())
        self._replace_series(
            replace(series, style=replace(series.style, color=color)),
            recompute=False,
            text="Change dataset color",
        )

    def _edit_style(self) -> None:
        if self._syncing or (series := self._series()) is None:
            return
        style = replace(
            series.style,
            line_style=self.line_style.currentData(),
            line_width=self.line_width.value(),
            symbol=None if self.symbol.currentData() == "none" else self.symbol.currentData(),
            symbol_size=self.symbol_size.value(),
            opacity=self.opacity.value(),
            show_error_bars=self.error_bars.isChecked(),
            error_width=self.error_width.value(),
        )
        self._replace_series(replace(series, style=style), recompute=False, text="Change dataset style")

    def _choose_error_color(self) -> None:
        series = self._series()
        if series is None:
            return
        selected = QColorDialog.getColor(
            QColor(*series.style.error_color),
            self,
            "Error-bar color",
            QColorDialog.ColorDialogOption.ShowAlphaChannel,
        )
        if not selected.isValid():
            return
        color = (selected.red(), selected.green(), selected.blue(), selected.alpha())
        self._replace_series(
            replace(series, style=replace(series.style, error_color=color)),
            recompute=False,
            text="Change error-bar color",
        )

    @staticmethod
    def _optional_float(field: QLineEdit) -> float | None:
        text = field.text().strip()
        return None if not text else float(text)

    def _edit_series_transform(self) -> None:
        if self._syncing or (series := self._series()) is None:
            return
        try:
            q_range = (self._optional_float(self.q_min), self._optional_float(self.q_max))
            replacement = replace(
                series,
                multiplier=self.multiplier.value(),
                offset=self.offset.value(),
                q_range=q_range,
            )
        except ValueError:
            self._sync_series_controls()
            return
        self._replace_series(replacement, recompute=True, text="Change displayed data")

    def _move_series(self, offset: int) -> None:
        if self._graph is None or (series_id := self.current_series_id()) is None:
            return
        items = list(self._graph.series)
        old = next(index for index, item in enumerate(items) if item.id == series_id)
        new = max(0, min(len(items) - 1, old + offset))
        if old == new:
            return
        items.insert(new, items.pop(old))
        graph = self._graph.replace_series(items)
        self._graph = graph
        self.graphChanged.emit(graph, False, "Reorder datasets")

    def _remove_series(self) -> None:
        if self._graph is None or (series_id := self.current_series_id()) is None:
            return
        graph = self._graph.replace_series(item for item in self._graph.series if item.id != series_id)
        self._graph = graph
        self.graphChanged.emit(graph, False, "Remove dataset from graph")

    def _add_annotation(self) -> None:
        if self._graph is None:
            return
        dialog = AnnotationDialog(parent=self)
        if dialog.exec() != dialog.DialogCode.Accepted:
            return
        graph = replace(self._graph, annotations=(*self._graph.annotations, dialog.value()))
        self._graph = graph
        self.graphChanged.emit(graph, False, "Add annotation")

    def _selected_annotation(self):
        item = self.annotations.currentItem()
        if item is None or self._graph is None:
            return None
        annotation_id = item.data(Qt.ItemDataRole.UserRole)
        return next(value for value in self._graph.annotations if value.id == annotation_id)

    def _edit_annotation(self) -> None:
        annotation = self._selected_annotation()
        if annotation is None or self._graph is None:
            return
        dialog = AnnotationDialog(annotation, self)
        if dialog.exec() != dialog.DialogCode.Accepted:
            return
        replacement = dialog.value()
        graph = replace(
            self._graph,
            annotations=tuple(
                replacement if value.id == replacement.id else value for value in self._graph.annotations
            ),
        )
        self._graph = graph
        self.graphChanged.emit(graph, False, "Edit annotation")

    def _delete_annotation(self) -> None:
        annotation = self._selected_annotation()
        if annotation is None or self._graph is None:
            return
        graph = replace(
            self._graph,
            annotations=tuple(value for value in self._graph.annotations if value.id != annotation.id),
        )
        self._graph = graph
        self.graphChanged.emit(graph, False, "Delete annotation")
