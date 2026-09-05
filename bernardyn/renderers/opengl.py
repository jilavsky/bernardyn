"""Isolated PyQtGraph OpenGL waterfall and surface renderer."""

from __future__ import annotations

import logging
import math
from pathlib import Path
from typing import Mapping

import numpy as np
from PySide6.QtCore import QBuffer, QByteArray, QIODevice
from PySide6.QtGui import QImage, QMatrix4x4
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from bernardyn.core.models import GraphDocument, PlotSeries

log = logging.getLogger(__name__)


def opengl_available() -> tuple[bool, str]:
    try:
        import OpenGL  # noqa: F401
        import pyqtgraph.opengl  # noqa: F401
    except Exception as exc:
        return False, str(exc)
    return True, "PyOpenGL and pyqtgraph.opengl are available"


def _projection_view_class(gl):
    class ProjectionView(gl.GLViewWidget):
        projection_mode = "perspective"

        def projectionMatrix(self, region, viewport):  # noqa: N802 - Qt API name
            if self.projection_mode != "orthographic":
                return super().projectionMatrix(region, viewport)
            x0, y0, width, height = viewport
            distance = float(self.opts["distance"])
            half_width = distance * math.tan(0.5 * math.radians(float(self.opts["fov"])))
            half_height = half_width * height / width
            left = half_width * ((region[0] - x0) * (2.0 / width) - 1)
            right = half_width * ((region[0] + region[2] - x0) * (2.0 / width) - 1)
            bottom = half_height * ((region[1] - y0) * (2.0 / height) - 1)
            top = half_height * ((region[1] + region[3] - y0) * (2.0 / height) - 1)
            matrix = QMatrix4x4()
            matrix.ortho(left, right, bottom, top, -distance * 1000, distance * 1000)
            return matrix

    return ProjectionView


class OpenGLPlotWidget(QWidget):
    renderer_id = "opengl"

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        from pyqtgraph import opengl as gl

        self._gl = gl
        self.view = _projection_view_class(gl)(self)
        self.caption = QLabel(self)
        self.caption.setStyleSheet("font-weight: bold; padding: 4px")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.caption)
        layout.addWidget(self.view, 1)
        self._items: list[object] = []
        self._graph: GraphDocument | None = None
        self._snapshots: dict[str, PlotSeries] = {}
        self._renderer_data: dict[str, np.ndarray] = {}
        self.render_warnings: list[str] = []

    def render(self, graph: GraphDocument, snapshots: Mapping[str, PlotSeries]) -> None:
        self._graph = graph
        self._snapshots = dict(snapshots)
        # The 3D renderers draw no annotations.  Say so rather than dropping
        # them without a word: a missing label otherwise looks like a bug in
        # the annotation itself.
        self.render_warnings = (
            [
                f"{len(graph.annotations)} annotation(s) are not drawn by the "
                f"3D renderer; switch the graph to the 2D plot to see them"
            ]
            if graph.annotations
            else []
        )
        for item in self._items:
            try:
                self.view.removeItem(item)
            except (RuntimeError, ValueError):
                pass
        self._items.clear()
        self._renderer_data.clear()
        self.caption.setText(graph.title)
        background = tuple(channel / 255 for channel in graph.background[:3])
        self.view.setBackgroundColor(background)
        camera = graph.renderer_config.get("camera", {})
        self.view.projection_mode = str(graph.renderer_config.get("projection", "perspective"))
        self.view.setCameraPosition(
            distance=float(camera.get("distance", 40.0)),
            elevation=float(camera.get("elevation", 25.0)),
            azimuth=float(camera.get("azimuth", -45.0)),
        )
        # These are plain strings from a combo box, never enum members, so
        # they are compared with == and are not exposed to the str-enum trap
        # documented above AnnotationKind in core/models.py.  An unrecognised
        # value still silently drew a waterfall, so report it instead.
        mode = graph.renderer_config.get(
            "mode", "surface" if graph.renderer_id == "opengl_surface" else "waterfall"
        )
        if mode not in ("surface", "waterfall"):
            message = f"Unknown 3D mode {mode!r}; drawing a waterfall instead"
            log.warning(message)
            self.render_warnings.append(message)
        visible = [
            (view, snapshots[view.id])
            for view in graph.series
            if view.visible and view.id in snapshots and len(snapshots[view.id].x)
        ]
        if mode == "surface" and len(visible) >= 2:
            self._render_surface(graph, visible)
        else:
            self._render_waterfall(graph, visible)
        if bool(graph.renderer_config.get("show_grid", True)):
            self._add_axes(len(visible))

    # Deliberately not named ``update``: that is Qt's own repaint slot.
    apply_graph = render

    def _display_coordinates(
        self, graph: GraphDocument, snapshot: PlotSeries
    ) -> tuple[np.ndarray, np.ndarray]:
        x = np.asarray(snapshot.x)
        z = np.asarray(snapshot.y)
        normalization = graph.renderer_config.get("normalization", "none")
        if normalization == "maximum":
            maximum = np.nanmax(np.abs(z))
            if maximum > 0:
                z = z / maximum
        elif normalization == "area" and len(x) > 1:
            order = np.argsort(x)
            area = abs(np.trapezoid(z[order], x[order]))
            if area > 0:
                z = z / area
        x = np.log10(x) if graph.x_axis.log else x
        z = np.log10(z) if graph.y_axis.log else z
        return x, z

    @staticmethod
    def _series_positions(graph: GraphDocument, visible) -> np.ndarray:
        spacing = float(graph.renderer_config.get("spacing", 1.0))
        configured = graph.renderer_config.get("series_positions", {})
        return np.asarray(
            [float(configured.get(view.id, index)) * spacing for index, (view, _) in enumerate(visible)],
            dtype=float,
        )

    def _render_waterfall(self, graph, visible) -> None:
        series_positions = self._series_positions(graph, visible)
        positions: list[np.ndarray] = []
        for series_position, (series_view, snapshot) in zip(series_positions, visible):
            x, z = self._display_coordinates(graph, snapshot)
            pos = np.column_stack((x, np.full_like(x, series_position), z))
            rgba = tuple(channel / 255 for channel in series_view.style.color)
            rgba = (*rgba[:3], rgba[3] * series_view.style.opacity)
            item = self._gl.GLLinePlotItem(
                pos=pos,
                color=rgba,
                width=max(1.0, series_view.style.line_width),
                antialias=True,
                mode="line_strip",
            )
            self.view.addItem(item)
            self._items.append(item)
            positions.append(pos)
        if positions:
            self._renderer_data["waterfall_positions"] = np.concatenate(positions)
            self._renderer_data["waterfall_lengths"] = np.asarray(
                [len(value) for value in positions], dtype=np.int64
            )
            self._renderer_data["series_axis"] = series_positions

    def _render_surface(self, graph, visible) -> None:
        coordinates = [self._display_coordinates(graph, snapshot) for _, snapshot in visible]
        lower = max(np.nanmin(x) for x, _ in coordinates)
        upper = min(np.nanmax(x) for x, _ in coordinates)
        if not np.isfinite(lower) or not np.isfinite(upper) or lower >= upper:
            self._render_waterfall(graph, visible)
            return
        samples = max(16, min(4096, int(graph.renderer_config.get("surface_samples", 512))))
        grid = np.linspace(lower, upper, samples)
        rows: list[np.ndarray] = []
        for x, z in coordinates:
            order = np.argsort(x)
            unique_x, unique_indices = np.unique(x[order], return_index=True)
            unique_z = z[order][unique_indices]
            rows.append(np.interp(grid, unique_x, unique_z))
        y = self._series_positions(graph, visible)
        surface = np.asarray(rows).T
        colors = np.empty((*surface.shape, 4), dtype=float)
        for column, (series_view, _) in enumerate(visible):
            rgba = np.asarray(series_view.style.color, dtype=float) / 255.0
            rgba[3] *= series_view.style.opacity
            colors[:, column, :] = rgba
        item = self._gl.GLSurfacePlotItem(
            x=grid,
            y=y,
            z=surface,
            colors=colors,
            smooth=False,
            computeNormals=False,
        )
        item.setGLOptions("translucent" if np.any(colors[..., 3] < 1) else "opaque")
        self.view.addItem(item)
        self._items.append(item)
        self._renderer_data.update(
            surface_x=grid,
            surface_y=y,
            surface_z=surface,
            surface_colors=colors,
        )

    def _add_axes(self, count: int) -> None:
        grid = self._gl.GLGridItem()
        grid.setSize(x=20, y=max(10, count * 2), z=1)
        self.view.addItem(grid)
        self._items.append(grid)
        axis = self._gl.GLAxisItem()
        axis.setSize(x=10, y=max(5, count), z=10)
        self.view.addItem(axis)
        self._items.append(axis)

    def capture_preview(self, width: int = 1600) -> bytes:
        old_size = self.view.size()
        if old_size.width() and width > old_size.width():
            height = max(1, round(old_size.height() * width / old_size.width()))
            self.view.resize(width, height)
        image = self.view.grabFramebuffer()
        if self.view.size() != old_size:
            self.view.resize(old_size)
        data = QByteArray()
        buffer = QBuffer(data)
        buffer.open(QIODevice.OpenModeFlag.WriteOnly)
        image.save(buffer, "PNG")
        return bytes(data)

    capture_snapshot = capture_preview

    def save_image(self, path: str | Path, width: int | None = None) -> Path:
        destination = Path(path)
        data = self.capture_preview(width or (self._graph.width_px if self._graph else 1600))
        image = QImage.fromData(data, "PNG")
        dpi = self._graph.dpi if self._graph else 300
        image.setDotsPerMeterX(round(dpi / 0.0254))
        image.setDotsPerMeterY(round(dpi / 0.0254))
        if image.isNull() or not image.save(str(destination)):
            raise OSError(f"could not save OpenGL image to {destination}")
        return destination

    def renderer_data(self) -> dict[str, np.ndarray]:
        return dict(self._renderer_data)

    def current_camera(self) -> dict[str, float]:
        return {
            "distance": float(self.view.opts["distance"]),
            "elevation": float(self.view.opts["elevation"]),
            "azimuth": float(self.view.opts["azimuth"]),
        }
