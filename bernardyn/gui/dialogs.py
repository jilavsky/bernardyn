"""Focused workbench dialogs that return domain values."""

from __future__ import annotations

from pathlib import Path
from typing import Mapping

import h5py
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QColorDialog,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from bernardyn.core.models import Annotation, AnnotationKind
from bernardyn.core.transforms import PlotTransform
from bernardyn.io.sources import ScatteringLocation


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
    def __init__(self, annotation: Annotation | None = None, parent=None) -> None:
        super().__init__(parent)
        self.annotation = annotation
        self.setWindowTitle("Graph annotation")
        self.kind = QComboBox(self)
        for value in AnnotationKind:
            self.kind.addItem(value.value.replace("_", " ").title(), value)
        self.text = QLineEdit(annotation.text if annotation else "", self)
        self.x = self._spin(annotation.position[0] if annotation else 1.0)
        self.y = self._spin(annotation.position[1] if annotation else 1.0)
        self.end_x = self._spin(annotation.end[0] if annotation and annotation.end else 2.0)
        self.end_y = self._spin(annotation.end[1] if annotation and annotation.end else 2.0)
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
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)

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
