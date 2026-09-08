"""One graph tab backed by a GraphDocument and renderer."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Mapping

import numpy as np
from PySide6.QtCore import QByteArray, QRect, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPalette, QPixmap
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


class GraphCanvas(QWidget):
    """Canvas-coloured frame that previews a graph's output aspect ratio."""

    RIGHT_STANDOFF_PX = 12

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._renderer = None
        self._aspect_ratio: float | None = None
        self.setAutoFillBackground(True)

    def set_renderer(self, renderer) -> None:
        if self._renderer is not None:
            self._renderer.hide()
        self._renderer = renderer
        if renderer is not None:
            renderer.setParent(self)
            renderer.show()
        self._layout_renderer()

    def set_graph_appearance(self, graph: GraphDocument, *, constrain_aspect: bool) -> None:
        # Plot-area-only backgrounds retain a white outer canvas, matching the
        # renderer's own canvas outside its coloured ViewBox.
        color = graph.background if graph.background_scope == "canvas" else (255, 255, 255, 255)
        palette = self.palette()
        palette.setColor(QPalette.ColorRole.Window, QColor(*color))
        self.setPalette(palette)
        self._aspect_ratio = graph.width_px / graph.height_px if constrain_aspect else None
        self._layout_renderer()

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt API
        super().resizeEvent(event)
        self._layout_renderer()

    def _layout_renderer(self) -> None:
        if self._renderer is None:
            return
        available = self.contentsRect().adjusted(0, 0, -self.RIGHT_STANDOFF_PX, 0)
        if available.width() <= 0 or available.height() <= 0:
            return
        width, height = available.width(), available.height()
        if self._aspect_ratio is not None:
            if width / height > self._aspect_ratio:
                width = round(height * self._aspect_ratio)
            else:
                height = round(width / self._aspect_ratio)
        x = available.x() + (available.width() - width) // 2
        y = available.y() + (available.height() - height) // 2
        self._renderer.setGeometry(QRect(x, y, width, height))


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
        self._layout.setContentsMargins(0, 0, 0, 0)
        self.canvas = GraphCanvas(self)
        self._layout.addWidget(self.canvas)
        self._build_renderer(graph)

    def _build_renderer(self, graph: GraphDocument) -> None:
        if self.renderer is not None:
            self.canvas.set_renderer(None)
            self.renderer.deleteLater()
        self.fallback_reason = None
        try:
            self.renderer = self.renderers.get(graph.renderer_id).create(self.canvas)
            self._renderer_id = graph.renderer_id
        except Exception as exc:
            self.fallback_reason = str(exc)
            self.renderer = Plot2DWidget(self.canvas)
            self._renderer_id = graph.renderer_id
        self.canvas.set_renderer(self.renderer)
        self.canvas.set_graph_appearance(
            graph, constrain_aspect=isinstance(self.renderer, Plot2DWidget)
        )

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
        self.canvas.set_graph_appearance(
            graph, constrain_aspect=isinstance(self.renderer, Plot2DWidget)
        )
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
