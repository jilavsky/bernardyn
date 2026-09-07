"""One graph tab backed by a GraphDocument and renderer."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Mapping

import numpy as np
from PySide6.QtCore import QByteArray, QRect, Qt
from PySide6.QtGui import QImage, QPainter, QPixmap
from PySide6.QtPrintSupport import QPrinter
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from bernardyn.core.models import GraphDocument, PlotSeries
from bernardyn.io.curve_export import export_displayed_csv, export_displayed_itx
from bernardyn.renderers import (
    OpenGLPlotWidget,
    Plot2DWidget,
    RendererRegistry,
    builtin_renderers,
)


class GraphPage(QWidget):
    def __init__(
        self,
        graph: GraphDocument,
        parent=None,
        *,
        renderers: RendererRegistry | None = None,
    ) -> None:
        super().__init__(parent)
        self.graph_id = graph.id
        self._graph = graph
        self._snapshots: dict[str, PlotSeries] = {}
        self.renderers = renderers or builtin_renderers()
        self.renderer = None
        self._renderer_id = ""
        self.fallback_reason: str | None = None
        self.render_warnings: list[str] = []
        self._layout = QVBoxLayout(self)
        # Keep the right boxed axis clear of an adjacent dock/widget edge.
        # The small standoff is visible only around the interactive canvas,
        # never added to exported graph dimensions.
        self._layout.setContentsMargins(0, 0, 10, 0)
        self._build_renderer(graph)

    def _build_renderer(self, graph: GraphDocument) -> None:
        if self.renderer is not None:
            self._layout.removeWidget(self.renderer)
            self.renderer.deleteLater()
        self.fallback_reason = None
        try:
            self.renderer = self.renderers.get(graph.renderer_id).create(self)
            self._renderer_id = graph.renderer_id
        except Exception as exc:
            self.fallback_reason = str(exc)
            self.renderer = Plot2DWidget(self)
            self._renderer_id = graph.renderer_id
        self._layout.addWidget(self.renderer)

    def render(self, graph: GraphDocument, snapshots: Mapping[str, PlotSeries]) -> None:
        self._graph = graph
        self._snapshots = dict(snapshots)
        if graph.renderer_id != self._renderer_id:
            self._build_renderer(graph)
        rendered_snapshots = snapshots
        if graph.renderer_id.startswith("opengl") and not isinstance(
            self.renderer, OpenGLPlotWidget
        ):
            spacing = float(graph.renderer_config.get("spacing", 1.0))
            rendered_snapshots = {
                view.id: replace(snapshot, y=snapshot.y + index * spacing)
                for index, view in enumerate(graph.series)
                if (snapshot := snapshots.get(view.id)) is not None
            }
        # ``apply_graph``, never ``update``: QWidget.update is Qt's repaint
        # slot and every widget has one, so getattr would silently find it.
        refresh = getattr(self.renderer, "apply_graph", None) or self.renderer.render
        refresh(graph, rendered_snapshots)
        self.render_warnings = list(getattr(self.renderer, "render_warnings", []))

    def capture_preview(self) -> bytes:
        capture = getattr(self.renderer, "capture_snapshot", None)
        return capture() if capture is not None else self.renderer.capture_preview()

    def save_image(self, path: str | Path) -> Path:
        return self.renderer.save_image(path)

    def copy_to_clipboard(self) -> None:
        if hasattr(self.renderer, "copy_to_clipboard"):
            self.renderer.copy_to_clipboard()
            return
        from PySide6.QtWidgets import QApplication

        pixmap = QPixmap()
        pixmap.loadFromData(QByteArray(self.capture_preview()), "PNG")
        QApplication.clipboard().setPixmap(pixmap)

    def print_to(self, printer: QPrinter) -> None:
        """Print a high-quality raster snapshot while preserving graph aspect."""
        image = QImage.fromData(self.capture_preview(), "PNG")
        if image.isNull():
            raise OSError("could not create a printable graph image")
        target = printer.pageRect(QPrinter.Unit.DevicePixel)
        size = image.size()
        size.scale(target.size(), Qt.AspectRatioMode.KeepAspectRatio)
        rect = QRect(
            target.x() + (target.width() - size.width()) // 2,
            target.y() + (target.height() - size.height()) // 2,
            size.width(),
            size.height(),
        )
        painter = QPainter(printer)
        try:
            painter.drawImage(rect, image)
        finally:
            painter.end()

    def export_csv(self, path: str | Path) -> Path:
        return export_displayed_csv(path, self._graph, self._snapshots)

    def export_itx(self, path: str | Path) -> Path:
        return export_displayed_itx(path, self._graph, self._snapshots)

    def renderer_data(self) -> dict[str, np.ndarray]:
        if hasattr(self.renderer, "renderer_data"):
            return self.renderer.renderer_data()
        return {}

    def current_renderer_config(self) -> dict | None:
        if not hasattr(self.renderer, "current_camera"):
            return None
        return {"camera": self.renderer.current_camera()}


class PreviewPage(QWidget):
    """Read-only preview for a package newer than this Bernardyn version."""

    def __init__(self, graph_id: str, png: bytes, parent=None) -> None:
        super().__init__(parent)
        self.graph_id = graph_id
        label = QLabel(self)
        label.setScaledContents(False)
        pixmap = QPixmap()
        pixmap.loadFromData(QByteArray(png), "PNG")
        label.setPixmap(pixmap)
        layout = QVBoxLayout(self)
        layout.addWidget(label)
