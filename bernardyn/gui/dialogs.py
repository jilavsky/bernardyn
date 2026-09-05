"""Focused workbench dialogs that return domain values."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Callable, Mapping

import h5py
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QColorDialog,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from bernardyn.core.models import Annotation, AnnotationKind
from bernardyn.core.transforms import PlotTransform
from bernardyn.io.file_browser import (
    DEFAULT_SORT_INDEX,
    FILE_TYPE_CHOICES,
    FILTER_PLACEHOLDER,
    FILTER_TOOLTIP,
    SORT_LABELS,
    SORT_TOOLTIP,
    files_in_folder,
    make_file_matcher,
    sort_paths,
)
from bernardyn.io.sources import ScatteringLocation


class DataFileSelectorDialog(QDialog):
    """Choose files and their plottable 1-D data without dialog cascades."""

    def __init__(
        self,
        folder: Path,
        discover: Callable[[Path], list[ScatteringLocation]],
        preferences: Mapping[str, object] | None = None,
        paths: list[Path] | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.folder = Path(folder)
        self._discover = discover
        self._fixed_paths = [Path(path) for path in paths] if paths is not None else None
        stored = dict(preferences or {})
        self._profiles: dict[str, list[int]] = {
            str(key): [int(index) for index in value]
            for key, value in dict(stored.get("dataset_profiles", {})).items()
            if isinstance(value, list)
        }
        self._locations: dict[Path, list[ScatteringLocation]] = {}
        self._errors: dict[Path, str] = {}
        self._current_path: Path | None = None
        self._syncing = False
        self.setWindowTitle(f"Select scattering data — {self.folder.name}")
        self.file_type = QComboBox(self)
        for label, value in FILE_TYPE_CHOICES:
            self.file_type.addItem(label, value)
        self.sort = QComboBox(self)
        self.sort.addItems(SORT_LABELS)
        self.sort.setToolTip(SORT_TOOLTIP)
        self.filter = QLineEdit(self)
        self.filter.setPlaceholderText(FILTER_PLACEHOLDER)
        self.filter.setToolTip(FILTER_TOOLTIP)
        self.count = QLabel(self)
        self.file_list = QListWidget(self)
        self.file_list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.file_list.currentItemChanged.connect(self._file_selected)
        self.file_list.itemDoubleClicked.connect(self._accept_selection)
        # Kept as an alias for small integrations written during beta development.
        self.list = self.file_list
        self.data_list = QListWidget(self)
        self.data_list.itemChanged.connect(self._data_selection_changed)
        self.data_list.setToolTip("Check one or more 1-D data sets to load from the selected file.")
        self.data_status = QLabel("Select a file to inspect its 1-D data.", self)
        self.data_status.setWordWrap(True)
        self.q_unit = QComboBox(self)
        self.q_unit.addItems(["1/A", "1/nm", "1/pm", "1/um", "1/mm"])
        self.error_fraction = QDoubleSpinBox(self)
        self.error_fraction.setRange(0.0001, 100.0)
        self.error_fraction.setDecimals(3)
        controls = QHBoxLayout()
        controls.addWidget(QLabel("File type:"))
        controls.addWidget(self.file_type)
        controls.addWidget(QLabel("Sort:"))
        controls.addWidget(self.sort)
        controls.addStretch()
        filter_row = QHBoxLayout()
        filter_row.addWidget(QLabel("Filter:"))
        filter_row.addWidget(self.filter, 1)
        select_all = QPushButton("Select all visible", self)
        select_all.clicked.connect(self._select_all_visible)
        filter_row.addWidget(select_all)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Open | QDialogButtonBox.StandardButton.Cancel,
            parent=self,
        )
        buttons.accepted.connect(self._accept_selection)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addWidget(
            QLabel(
                f"Folder: {self.folder}\n"
                "Select files on the left, then select the desired 1-D data on the right. "
                "Choices are reused for files with the same layout."
            )
        )
        layout.addLayout(controls)
        layout.addLayout(filter_row)
        lists = QHBoxLayout()
        left = QVBoxLayout()
        left.addWidget(QLabel("Files"))
        left.addWidget(self.file_list, 1)
        right = QVBoxLayout()
        right.addWidget(QLabel("1-D data in selected file"))
        right.addWidget(self.data_list, 1)
        right.addWidget(self.data_status)
        lists.addLayout(left, 1)
        lists.addLayout(right, 1)
        layout.addLayout(lists, 1)
        layout.addWidget(self.count)
        options = QHBoxLayout()
        options.addWidget(QLabel("Q unit when missing:"))
        options.addWidget(self.q_unit)
        options.addSpacing(12)
        options.addWidget(QLabel("Missing intensity uncertainty (%):"))
        options.addWidget(self.error_fraction)
        options.addStretch()
        layout.addLayout(options)
        layout.addWidget(buttons)
        self.file_type.setCurrentIndex(
            max(0, self.file_type.findData(stored.get("file_type", "all")))
        )
        self.sort.setCurrentIndex(int(stored.get("sort_index", DEFAULT_SORT_INDEX)))
        self.filter.setText(str(stored.get("filter", "")))
        self.q_unit.setCurrentIndex(max(0, self.q_unit.findText(str(stored.get("q_unit", "1/A")))))
        self.error_fraction.setValue(float(stored.get("error_percent", 5.0)))
        self.file_type.currentIndexChanged.connect(self._refresh)
        self.sort.currentIndexChanged.connect(self._refresh)
        self.filter.textChanged.connect(self._apply_filter)
        self.resize(1040, 580)
        self._refresh()

    def _refresh(self) -> None:
        paths = (
            self._fixed_paths
            if self._fixed_paths is not None
            else files_in_folder(self.folder, str(self.file_type.currentData()))
        )
        paths = sort_paths(paths, self.sort.currentIndex())
        self.file_list.clear()
        for path in paths:
            item = QListWidgetItem(path.name)
            item.setData(Qt.ItemDataRole.UserRole, path)
            item.setToolTip(str(path))
            self.file_list.addItem(item)
        self._apply_filter()

    def _apply_filter(self) -> None:
        matches = make_file_matcher(self.filter.text())
        visible = 0
        for index in range(self.file_list.count()):
            item = self.file_list.item(index)
            hidden = not matches(item.text())
            item.setHidden(hidden)
            visible += not hidden
        self.count.setText(f"Showing {visible} of {self.file_list.count()} files")

    def _select_all_visible(self) -> None:
        self.file_list.clearSelection()
        for index in range(self.file_list.count()):
            item = self.file_list.item(index)
            item.setSelected(not item.isHidden())

    def selected_paths(self) -> list[Path]:
        return [Path(item.data(Qt.ItemDataRole.UserRole)) for item in self.file_list.selectedItems()]

    @staticmethod
    def _profile_key(locations: list[ScatteringLocation]) -> str:
        # NXcanSAS commonly stores curves as ``entry/<sample>/sasdata``. The
        # sample component changes from file to file, whereas the leaf group,
        # curve order, and variant identify the practical loading layout.
        shape = []
        for location in locations:
            parts = tuple(part for part in (location.internal_path or "").split("/") if part)
            shape.append((parts[-1] if parts else "", location.variant))
        return json.dumps(shape, separators=(",", ":"))

    def _locations_for(self, path: Path) -> list[ScatteringLocation]:
        if path not in self._locations and path not in self._errors:
            try:
                self._locations[path] = self._discover(path)
            except Exception as exc:
                self._errors[path] = str(exc)
        return self._locations.get(path, [])

    def _file_selected(self, current: QListWidgetItem | None, previous=None) -> None:
        self._current_path = None if current is None else Path(current.data(Qt.ItemDataRole.UserRole))
        self._populate_data_list()

    def _populate_data_list(self) -> None:
        self._syncing = True
        self.data_list.clear()
        path = self._current_path
        if path is None:
            self.data_status.setText("Select a file to inspect its 1-D data.")
            self._syncing = False
            return
        locations = self._locations_for(path)
        if not locations:
            self.data_status.setText(self._errors.get(path, "No plottable 1-D data was found."))
            self._syncing = False
            return
        profile = self._profiles.get(self._profile_key(locations))
        checked = set(profile if profile is not None else ([0] if len(locations) == 1 else []))
        for index, location in enumerate(locations):
            path_text = location.internal_path or "top-level data"
            unit_note = " — Q unit missing" if location.metadata.get("q_unit_missing") else ""
            item = QListWidgetItem(f"{location.display_name}  [{path_text}]{unit_note}")
            item.setData(Qt.ItemDataRole.UserRole, index)
            item.setToolTip(f"{location.display_name}\nHDF5 path: {path_text}")
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked if index in checked else Qt.CheckState.Unchecked)
            self.data_list.addItem(item)
        instruction = "Select one or more data sets to load."
        if profile is not None:
            instruction += " Reused from a previous file with this layout."
        elif len(locations) > 1:
            instruction += " No automatic choice is made for a multi-data file."
        self.data_status.setText(instruction)
        self._syncing = False

    def _data_selection_changed(self, item: QListWidgetItem) -> None:
        if self._syncing or self._current_path is None:
            return
        locations = self._locations_for(self._current_path)
        if not locations:
            return
        selected = [
            int(self.data_list.item(index).data(Qt.ItemDataRole.UserRole))
            for index in range(self.data_list.count())
            if self.data_list.item(index).checkState() == Qt.CheckState.Checked
        ]
        self._profiles[self._profile_key(locations)] = selected

    def selected_locations(self) -> list[ScatteringLocation]:
        selected: list[ScatteringLocation] = []
        for path in self.selected_paths():
            locations = self._locations_for(path)
            profile = self._profiles.get(self._profile_key(locations), [])
            selected.extend(
                location for index, location in enumerate(locations) if index in profile
            )
        return selected

    def unresolved_paths(self) -> list[Path]:
        unresolved = []
        for path in self.selected_paths():
            locations = self._locations_for(path)
            if len(locations) > 1 and not self._profiles.get(self._profile_key(locations), []):
                unresolved.append(path)
        return unresolved

    def preferences(self) -> dict[str, object]:
        return {
            "file_type": self.file_type.currentData(),
            "sort_index": self.sort.currentIndex(),
            "filter": self.filter.text(),
            "q_unit": self.q_unit.currentText(),
            "error_percent": self.error_fraction.value(),
            "dataset_profiles": self._profiles,
        }

    def _accept_selection(self) -> None:
        if not self.selected_paths():
            QMessageBox.information(self, "Select scattering data", "Select one or more files to load.")
            return
        unresolved = self.unresolved_paths()
        if unresolved:
            QMessageBox.information(
                self,
                "Choose 1-D data",
                "Select a representative file and check the data sets to load before continuing.\n\n"
                f"No selection has been made for: {unresolved[0].name}",
            )
            return
        if not self.selected_locations():
            QMessageBox.information(self, "Choose 1-D data", "No data sets are selected for loading.")
            return
        self.accept()


class LocationDialog(QDialog):
    def __init__(self, locations: list[ScatteringLocation], parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Select HDF5 datasets")
        self.list = QListWidget(self)
        for location in locations:
            item = QListWidgetItem(location.display_name)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked)
            item.setData(Qt.ItemDataRole.UserRole, location)
            self.list.addItem(item)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            parent=self,
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Choose one or more datasets to add to the active graph:"))
        layout.addWidget(self.list)
        layout.addWidget(buttons)
        self.resize(650, 360)

    def selected(self) -> list[ScatteringLocation]:
        return [
            self.list.item(index).data(Qt.ItemDataRole.UserRole)
            for index in range(self.list.count())
            if self.list.item(index).checkState() == Qt.CheckState.Checked
        ]


class GraphSelectionDialog(QDialog):
    def __init__(self, graphs: list[tuple[str, str]], parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Import graphs")
        self.list = QListWidget(self)
        for graph_id, title in graphs:
            item = QListWidgetItem(title)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked)
            item.setData(Qt.ItemDataRole.UserRole, graph_id)
            self.list.addItem(item)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            parent=self,
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Choose one or more graphs to import:"))
        layout.addWidget(self.list)
        layout.addWidget(buttons)
        self.resize(520, 320)

    def selected_ids(self) -> list[str]:
        return [
            str(self.list.item(index).data(Qt.ItemDataRole.UserRole))
            for index in range(self.list.count())
            if self.list.item(index).checkState() == Qt.CheckState.Checked
        ]


class HDFMappingDialog(QDialog):
    def __init__(self, path: Path, parent=None) -> None:
        super().__init__(parent)
        self.path = path
        self.setWindowTitle(f"Map HDF5 arrays — {path.name}")
        numeric: list[str] = []
        with h5py.File(path, "r") as handle:
            def visitor(name, obj):
                if isinstance(obj, h5py.Dataset) and obj.ndim == 1 and obj.dtype.kind in "iuf":
                    numeric.append("/" + name)
            handle.visititems(visitor)
        self.q = QComboBox(self)
        self.intensity = QComboBox(self)
        self.uncertainty = QComboBox(self)
        self.dq = QComboBox(self)
        for box in (self.q, self.intensity):
            box.addItems(numeric)
        for box in (self.uncertainty, self.dq):
            box.addItem("Not present")
            box.addItems(numeric)
        form = QFormLayout()
        form.addRow("Q:", self.q)
        form.addRow("Intensity:", self.intensity)
        form.addRow("Uncertainty:", self.uncertainty)
        form.addRow("dQ:", self.dq)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            parent=self,
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Choose one-dimensional numeric datasets:"))
        layout.addLayout(form)
        layout.addWidget(buttons)
        if len(numeric) < 2:
            buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(False)

    def location(self) -> ScatteringLocation:
        mapping = {"q": self.q.currentText(), "intensity": self.intensity.currentText()}
        if self.uncertainty.currentIndex() > 0:
            mapping["uncertainty"] = self.uncertainty.currentText()
        if self.dq.currentIndex() > 0:
            mapping["dq"] = self.dq.currentText()
        return ScatteringLocation(
            path=self.path,
            adapter_id="hdf5",
            internal_path="/",
            display_name=f"{self.path.name}: custom mapping",
            variant="custom",
            metadata={"mapping": mapping},
        )


class TransformParameterDialog(QDialog):
    def __init__(self, transform: PlotTransform, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(transform.name)
        self.inputs: dict[str, QDoubleSpinBox] = {}
        form = QFormLayout()
        for parameter in transform.parameters:
            spin = QDoubleSpinBox(self)
            spin.setDecimals(8)
            spin.setRange(parameter.minimum or -1e300, 1e300)
            spin.setValue(parameter.default or max(parameter.minimum or 0.0, 1.0))
            self.inputs[parameter.id] = spin
            form.addRow(parameter.label + ":", spin)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            parent=self,
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)

    def values(self) -> dict[str, float]:
        return {name: spin.value() for name, spin in self.inputs.items()}


class SeriesTransformParameterDialog(QDialog):
    """Declarative per-series transform parameters in one compact table."""

    def __init__(
        self,
        transform: PlotTransform,
        rows: list[tuple[str, str, Mapping[str, float]]],
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"{transform.name} parameters")
        self.inputs: dict[str, dict[str, QDoubleSpinBox]] = {}
        table = QTableWidget(len(rows), len(transform.parameters) + 1, self)
        table.setHorizontalHeaderLabels(
            ["Dataset", *(parameter.label for parameter in transform.parameters)]
        )
        for row_index, (series_id, label, initial) in enumerate(rows):
            table.setItem(row_index, 0, QTableWidgetItem(label))
            self.inputs[series_id] = {}
            for column, parameter in enumerate(transform.parameters, 1):
                spin = QDoubleSpinBox(table)
                spin.setDecimals(8)
                spin.setRange(parameter.minimum or -1e300, 1e300)
                value = initial.get(parameter.id, parameter.default)
                spin.setValue(value if value is not None else max(parameter.minimum or 0.0, 1.0))
                table.setCellWidget(row_index, column, spin)
                self.inputs[series_id][parameter.id] = spin
        table.resizeColumnsToContents()
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            parent=self,
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addWidget(
            QLabel("Values found in PyIrena result metadata are used as initial values.")
        )
        layout.addWidget(table)
        layout.addWidget(buttons)
        self.resize(max(520, table.horizontalHeader().length() + 80), 140 + 42 * len(rows))

    def values(self) -> dict[str, dict[str, float]]:
        return {
            series_id: {name: spin.value() for name, spin in controls.items()}
            for series_id, controls in self.inputs.items()
        }


class AnnotationDialog(QDialog):
    def __init__(
        self,
        annotation: Annotation | None = None,
        *,
        default_position: tuple[float, float] | None = None,
        default_end: tuple[float, float] | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.annotation = annotation
        self.setWindowTitle("Graph annotation")
        self.setSizeGripEnabled(True)
        self.kind = QComboBox(self)
        for value in AnnotationKind:
            self.kind.addItem(value.value.replace("_", " ").title(), value)
        position = annotation.position if annotation else (default_position or (1.0, 1.0))
        end = annotation.end if annotation and annotation.end else (default_end or (2.0, 2.0))
        self.text = QLineEdit(annotation.text if annotation else "", self)
        self.x = self._spin(position[0])
        self.y = self._spin(position[1])
        self.end_x = self._spin(end[0])
        self.end_y = self._spin(end[1])
        self._color = annotation.color if annotation else (20, 20, 20, 255)
        self.color = QPushButton("Choose…", self)
        self.color.clicked.connect(self._choose_color)
        self._update_color_button()
        self.line_width = self._spin(annotation.line_width if annotation else 1.5)
        self.line_width.setRange(0.1, 50)
        self.font_size = QSpinBox(self)
        self.font_size.setRange(6, 144)
        self.font_size.setValue(annotation.font_size if annotation else 11)
        self.z_order = QSpinBox(self)
        self.z_order.setRange(-10_000, 10_000)
        self.z_order.setValue(annotation.z_order if annotation else 10)
        if annotation:
            self.kind.setCurrentIndex(self.kind.findData(annotation.kind))
        form = QFormLayout()
        form.addRow("Type:", self.kind)
        form.addRow("Text:", self.text)
        form.addRow("X:", self.x)
        form.addRow("Y:", self.y)
        form.addRow("Arrow end X:", self.end_x)
        form.addRow("Arrow end Y:", self.end_y)
        form.addRow("Color:", self.color)
        form.addRow("Line width:", self.line_width)
        form.addRow("Font size:", self.font_size)
        form.addRow("Z order:", self.z_order)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            parent=self,
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form_widget = QWidget(self)
        form_widget.setLayout(form)
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setWidget(form_widget)
        scroll.setMaximumHeight(300)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Coordinates are in the plotted data units; defaults are placed within the data."))
        layout.addWidget(scroll, 1)
        layout.addWidget(buttons)
        self.resize(460, 420)

    def _spin(self, value: float) -> QDoubleSpinBox:
        spin = QDoubleSpinBox(self)
        spin.setDecimals(8)
        spin.setRange(-1e300, 1e300)
        spin.setValue(value)
        return spin

    def value(self) -> Annotation:
        kind = self.kind.currentData()
        end = (self.end_x.value(), self.end_y.value()) if kind is AnnotationKind.ARROW else None
        options = {
            "kind": kind,
            "position": (self.x.value(), self.y.value()),
            "end": end,
            "text": self.text.text(),
            "color": self._color,
            "line_width": self.line_width.value(),
            "font_size": self.font_size.value(),
            "z_order": self.z_order.value(),
        }
        if self.annotation is not None:
            options["id"] = self.annotation.id
        return Annotation(**options)

    def _choose_color(self) -> None:
        selected = QColorDialog.getColor(
            QColor(*self._color),
            self,
            "Annotation color",
            QColorDialog.ColorDialogOption.ShowAlphaChannel,
        )
        if selected.isValid():
            self._color = (
                selected.red(),
                selected.green(),
                selected.blue(),
                selected.alpha(),
            )
            self._update_color_button()

    def _update_color_button(self) -> None:
        self.color.setStyleSheet(
            f"background: rgba({self._color[0]}, {self._color[1]}, "
            f"{self._color[2]}, {self._color[3]})"
        )
