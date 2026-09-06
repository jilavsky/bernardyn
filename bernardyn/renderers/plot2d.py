"""Publication-oriented two-dimensional PyQtGraph renderer."""

from __future__ import annotations

import csv
import logging
import math
from dataclasses import replace
from pathlib import Path
from typing import Mapping

import numpy as np
import pyqtgraph as pg
import pyqtgraph.exporters
from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QRect, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QFont, QPainter
from PySide6.QtSvg import QSvgGenerator
from PySide6.QtWidgets import QApplication

from bernardyn.core.models import Annotation, AnnotationKind, GraphDocument, PlotSeries, SeriesStyle

log = logging.getLogger(__name__)

# Annotations sit above every curve, error bar and legend.  The document's
# own ``z_order`` only orders annotations against each other.
ANNOTATION_BASE_Z = 100_000

LINE_STYLES = {
    "none": Qt.PenStyle.NoPen,
    "solid": Qt.PenStyle.SolidLine,
    "dash": Qt.PenStyle.DashLine,
    "dot": Qt.PenStyle.DotLine,
    "dash-dot": Qt.PenStyle.DashDotLine,
}


class PublicationAxisItem(pg.AxisItem):
    """Axis labels without SI-prefix multipliers and with predictable exponent use."""

    def __init__(self, orientation: str, **kwargs) -> None:
        super().__init__(orientation, **kwargs)
        self.disable_auto_si_prefix()

    def disable_auto_si_prefix(self) -> None:
        """Disable and fully clear PyQtGraph's persisted SI tick scaling.

        ``enableAutoSIPrefix(False)`` recalculates ``autoSIPrefixScale`` from
        the *previous* view range in PyQtGraph 0.14.  With auto-prefixes then
        disabled, the next range change does not reset that scale.  A rerender
        can consequently show correct geometry with labels shifted by factors
        such as 1000 or 1e-9.
        """
        self.autoSIPrefix = False
        self.autoSIPrefixScale = 1.0
        self.labelUnitPrefix = ""

    def tickStrings(self, values, scale, spacing):  # noqa: N802 - Qt/PyQtGraph API
        if self.logMode:
            return super().tickStrings(values, scale, spacing)
        scaled_spacing = abs(spacing * scale)
        places = max(0, min(12, math.ceil(-math.log10(scaled_spacing)))) if scaled_spacing else 6
        labels = []
        for value in values:
            displayed = value * scale
            magnitude = abs(displayed)
            if displayed == 0:
                labels.append("0")
            elif 1e-4 <= magnitude <= 1e3:
                text = f"{displayed:.{places}f}"
                # Do not remove significant zeroes from integer ticks:
                # 100 must not become 1.
                labels.append(text.rstrip("0").rstrip(".") if "." in text else text)
            else:
                labels.append(f"{displayed:.3e}")
        return labels


def _color(value: tuple[int, int, int, int], opacity: float = 1.0) -> QColor:
    red, green, blue, alpha = value
    return QColor(red, green, blue, round(alpha * opacity))


def _pen(style: SeriesStyle):
    if style.line_style == "none" or style.line_width <= 0:
        return None
    return pg.mkPen(
        _color(style.color, style.opacity),
        width=style.line_width,
        style=LINE_STYLES.get(style.line_style, Qt.PenStyle.SolidLine),
    )


def _coordinate(values: np.ndarray, logarithmic: bool) -> np.ndarray:
    return np.log10(values) if logarithmic else values


class Plot2DWidget(pg.PlotWidget):
    renderer_id = "plot2d"

    def __init__(self, parent=None) -> None:
        super().__init__(
            parent=parent,
            background="w",
            axisItems={
                "bottom": PublicationAxisItem("bottom"),
                "left": PublicationAxisItem("left"),
                "top": PublicationAxisItem("top"),
                "right": PublicationAxisItem("right"),
            },
        )
        self.setAntialiasing(True)
        self.getPlotItem().setMenuEnabled(True)
        self._graph: GraphDocument | None = None
        self._snapshots: dict[str, PlotSeries] = {}
        self._legend = None
        self._curve_items: dict[str, pg.PlotDataItem] = {}
        self._error_items: dict[str, pg.ErrorBarItem] = {}
        # Problems met during the last render.  Curves, annotations and axis
        # ranges are drawn independently, so a failure in one must be
        # reported rather than silently truncating the rest of the plot.
        self.render_warnings: list[str] = []
        self._annotation_items: list[tuple[Annotation, object]] = []

    def render(self, graph: GraphDocument, snapshots: Mapping[str, PlotSeries]) -> None:
        self._graph = graph
        self._snapshots = dict(snapshots)
        self.render_warnings = []
        plot = self.getPlotItem()
        # PlotDataItem clipping/downsampling is view-dependent. Leaving
        # PyQtGraph's persistent auto-range enabled makes the view rescale
        # against its newly clipped bounds, which can visibly oscillate.
        # Bernardyn computes an automatic range once after the complete graph
        # is installed instead; a later graph/data edit invokes render again.
        plot.enableAutoRange(x=False, y=False)
        plot.clear()
        self._curve_items.clear()
        self._error_items.clear()
        # PlotItem.clear() removes data items but not its legend.  Removing a
        # legend from the scene without clearing plot.legend makes the next
        # addLegend() return a detached object, leaving legend controls with
        # no visible effect after the first render.
        self._remove_legend(plot)
        self.setBackground(_color(graph.background))
        plot.setTitle(
            graph.title,
            color=_color(graph.x_axis.color).name(),
            **{
                "font-size": f"{graph.typography.title_size}pt",
                "font-family": graph.typography.family,
            },
        )
        plot.setLabel(
            "bottom",
            graph.x_axis.label,
            color=_color(graph.x_axis.color).name(),
            **{
                "font-size": f"{graph.typography.axis_label_size}pt",
                "font-family": graph.typography.family,
            },
        )
        plot.setLabel(
            "left",
            graph.y_axis.label,
            color=_color(graph.y_axis.color).name(),
            **{
                "font-size": f"{graph.typography.axis_label_size}pt",
                "font-family": graph.typography.family,
            },
        )
        tick_font = QFont(graph.typography.family, graph.typography.tick_size)
        for axis_name, spec in (("bottom", graph.x_axis), ("left", graph.y_axis)):
            axis = plot.getAxis(axis_name)
            axis.disable_auto_si_prefix()
            axis.setTickFont(tick_font)
            axis.setPen(pg.mkPen(_color(spec.color), width=spec.thickness))
            axis.setTextPen(pg.mkPen(_color(spec.color)))
            # AxisItem uses rendered font metrics and available axis length
            # to omit crowded lower-level labels.  Level 0 keeps major labels
            # only while retaining minor tick marks.
            axis.setStyle(maxTextLevel=2 if spec.minor_tick_labels else 0)
        for axis_name, spec in (("top", graph.x_axis), ("right", graph.y_axis)):
            axis = plot.getAxis(axis_name)
            axis.disable_auto_si_prefix()
            axis.setTickFont(tick_font)
            axis.setPen(pg.mkPen(_color(spec.color), width=spec.thickness))
            axis.setTextPen(pg.mkPen(_color(spec.color)))
            axis.setStyle(showValues=False)
            plot.showAxis(axis_name, graph.box_axes)
        plot.showGrid(
            x=graph.x_axis.grid_major,
            y=graph.y_axis.grid_major,
            alpha=0.25,
        )
        plot.setLogMode(x=graph.x_axis.log, y=graph.y_axis.log)
        if graph.legend.visible:
            offsets = {
                "top-right": (-12, 12),
                "top-left": (12, 12),
                "bottom-right": (-12, -12),
                "bottom-left": (12, -12),
            }
            self._legend = plot.addLegend(
                offset=offsets.get(graph.legend.position, (-12, 12)),
                colCount=graph.legend.columns,
            )
            self._legend.setLabelTextSize(f"{graph.typography.legend_size}pt")
            if graph.legend.framed:
                self._legend.setBrush(pg.mkBrush(255, 255, 255, 220))
                self._legend.setPen(pg.mkPen(90, 90, 90))

        for view in graph.series:
            if not view.visible or view.id not in snapshots:
                continue
            snapshot = snapshots[view.id]
            try:
                self._add_series(plot, graph, view.id, snapshot, view.style)
            except Exception as exc:  # pragma: no cover - depends on Qt/PyQtGraph
                # A curve that cannot be drawn must not take the annotations
                # and the axis ranges down with it: those are drawn after this
                # loop, and Qt swallows exceptions raised inside slots.
                log.exception("Could not draw series %r", snapshot.label)
                self.render_warnings.append(f"Could not draw {snapshot.label!r}: {exc}")
        try:
            self._add_annotations(graph)
        except Exception as exc:  # pragma: no cover - depends on Qt/PyQtGraph
            log.exception("Could not draw annotations")
            self.render_warnings.append(f"Could not draw annotations: {exc}")
        try:
            self._apply_ranges(graph)
        except Exception as exc:  # pragma: no cover - depends on Qt/PyQtGraph
            log.exception("Could not apply axis ranges")
            self.render_warnings.append(f"Could not apply axis ranges: {exc}")
        # Only meaningful once the axis ranges are final.
        try:
            self._review_annotations(graph)
        except Exception:  # pragma: no cover - diagnostics must never break a plot
            log.exception("Could not review annotation placement")

    def _remove_legend(self, plot) -> None:
        """Fully dispose of PyQtGraph's out-of-band legend item."""
        legend = plot.legend
        if legend is not None:
            try:
                scene = legend.scene()
                if scene is not None:
                    scene.removeItem(legend)
            except RuntimeError:
                pass
        plot.legend = None
        self._legend = None

    def _add_series(
        self,
        plot: pg.PlotItem,
        graph: GraphDocument,
        series_id: str,
        snapshot: PlotSeries,
        style: SeriesStyle,
    ) -> None:
        symbol = None if style.symbol in (None, "none") else style.symbol
        item = pg.PlotDataItem(
            snapshot.x,
            snapshot.y,
            name=snapshot.label,
            pen=_pen(style),
            symbol=symbol,
            symbolSize=style.symbol_size,
            symbolPen=pg.mkPen(_color(style.color, style.opacity)),
            symbolBrush=pg.mkBrush(_color(style.color, style.opacity)),
            connect="finite",
        )
        plot.addItem(item)
        self._curve_items[series_id] = item
        item.setDownsampling(auto=True, method="peak")
        item.setClipToView(True)
        if style.show_error_bars and (snapshot.dx is not None or snapshot.dy is not None):
            error = self._add_error_bars(graph, snapshot, style)
            if error is not None:
                self._error_items[series_id] = error

    def apply_graph(self, graph: GraphDocument, snapshots: Mapping[str, PlotSeries]) -> None:
        """Refresh the plot for ``graph``, restyling in place where possible.

        Deliberately not named ``update``: that is Qt's own repaint slot on
        QWidget, and overriding it with a different signature breaks every
        caller that schedules a repaint the normal way.
        """
        if not self._can_update_style_only(graph, snapshots):
            self.render(graph, snapshots)
            return
        self._graph = graph
        self._snapshots = dict(snapshots)
        for view in graph.series:
            item = self._curve_items[view.id]
            style = view.style
            symbol = None if style.symbol in (None, "none") else style.symbol
            item.setPen(_pen(style))
            item.setSymbol(symbol)
            item.setSymbolSize(style.symbol_size)
            item.setSymbolPen(pg.mkPen(_color(style.color, style.opacity)))
            item.setSymbolBrush(pg.mkBrush(_color(style.color, style.opacity)))
            error = self._error_items.get(view.id)
            if error is not None:
                error.setOpts(
                    pen=pg.mkPen(_color(style.error_color), width=style.error_width)
                )

    def _can_update_style_only(
        self, graph: GraphDocument, snapshots: Mapping[str, PlotSeries]
    ) -> bool:
        previous = self._graph
        if previous is None or set(snapshots) != set(self._snapshots):
            return False
        if any(snapshots[key] is not self._snapshots[key] for key in snapshots):
            return False
        if replace(previous, series=()) != replace(graph, series=()):
            return False
        if len(previous.series) != len(graph.series):
            return False
        for old, new in zip(previous.series, graph.series):
            if replace(old, style=new.style) != new:
                return False
            if old.style.show_error_bars != new.style.show_error_bars:
                return False
            if new.id not in self._curve_items:
                return False
        return True

    def _add_error_bars(
        self, graph: GraphDocument, snapshot: PlotSeries, style: SeriesStyle
    ) -> pg.ErrorBarItem | None:
        x = _coordinate(snapshot.x, graph.x_axis.log)
        y = _coordinate(snapshot.y, graph.y_axis.log)
        options: dict[str, np.ndarray | float] = {"x": x, "y": y, "beam": 0.0}
        valid = np.isfinite(x) & np.isfinite(y)
        if snapshot.dy is not None:
            if graph.y_axis.log:
                upper = snapshot.y + snapshot.dy
                lower = snapshot.y - snapshot.dy
                valid &= (upper > 0) & (lower > 0)
                options["top"] = np.log10(upper) - y
                options["bottom"] = y - np.log10(lower)
            else:
                options["top"] = snapshot.dy
                options["bottom"] = snapshot.dy
        if snapshot.dx is not None:
            if graph.x_axis.log:
                right = snapshot.x + snapshot.dx
                left = snapshot.x - snapshot.dx
                valid &= (right > 0) & (left > 0)
                options["right"] = np.log10(right) - x
                options["left"] = x - np.log10(left)
            else:
                options["right"] = snapshot.dx
                options["left"] = snapshot.dx
        for key, value in tuple(options.items()):
            if isinstance(value, np.ndarray):
                options[key] = value[valid]
        if not np.any(valid):
            return None
        error = pg.ErrorBarItem(
            **options,
            pen=pg.mkPen(_color(style.error_color), width=style.error_width),
        )
        self.getPlotItem().addItem(error)
        return error

    def _add_annotations(self, graph: GraphDocument) -> None:
        plot = self.getPlotItem()
        self._annotation_items = []
        log.debug("drawing %d annotation(s)", len(graph.annotations))
        for annotation in graph.annotations:
            try:
                self._add_annotation(plot, graph, annotation)
            except Exception as exc:  # pragma: no cover - depends on Qt/PyQtGraph
                log.exception("Could not draw annotation %r", annotation.id)
                label = annotation.text or annotation.kind.value
                self.render_warnings.append(f"Could not draw annotation {label!r}: {exc}")

    def _add_annotation(
        self, plot: pg.PlotItem, graph: GraphDocument, annotation: Annotation
    ) -> None:
        # Annotations are plot-view overlays, not canvas decorations.  Keep
        # them out of automatic range calculations and above every curve,
        # error bar, legend, and the plot background.  The document's own
        # z_order only orders annotations against each other.
        overlay_z = ANNOTATION_BASE_Z + annotation.z_order

        def add_overlay(item) -> None:
            item.setZValue(overlay_z)
            plot.addItem(item, ignoreBounds=True)
            self._annotation_items.append((annotation, item))

        color = _color(annotation.color)
        x, y = self._plot_position(graph, annotation.position)
        if annotation.kind is AnnotationKind.TEXT:
            item = pg.TextItem(annotation.text, color=color, anchor=(0, 1))
            item.setFont(QFont(graph.typography.family, annotation.font_size))
            item.setPos(x, y)
            add_overlay(item)
        elif annotation.kind is AnnotationKind.HLINE:
            add_overlay(
                pg.InfiniteLine(
                    pos=y,
                    angle=0,
                    pen=pg.mkPen(color, width=annotation.line_width),
                    movable=False,
                )
            )
        elif annotation.kind is AnnotationKind.VLINE:
            add_overlay(
                pg.InfiniteLine(
                    pos=x,
                    angle=90,
                    pen=pg.mkPen(color, width=annotation.line_width),
                    movable=False,
                )
            )
        elif annotation.kind is AnnotationKind.ARROW:
            if annotation.end is None:  # pragma: no cover - blocked by the model
                raise ValueError("arrow annotation has no end point")
            end_x, end_y = self._plot_position(graph, annotation.end)
            add_overlay(
                pg.PlotCurveItem(
                    [x, end_x],
                    [y, end_y],
                    pen=pg.mkPen(color, width=annotation.line_width),
                )
            )
            angle = math.degrees(math.atan2(end_y - y, end_x - x))
            arrow = pg.ArrowItem(
                pos=(end_x, end_y), angle=180 - angle, brush=color, pen=color
            )
            add_overlay(arrow)
        else:
            # No branch matched, so nothing was drawn.  Never let that pass
            # quietly: an annotation that is in the document but not on the
            # canvas looks identical to a rendering bug from every side.
            message = (
                f"Annotation kind {annotation.kind!r} was not drawn "
                f"(no renderer branch matched)"
            )
            log.warning(message)
            self.render_warnings.append(message)

    @staticmethod
    def _plot_position(
        graph: GraphDocument, position: tuple[float, float]
    ) -> tuple[float, float]:
        """Data coordinates in the plot's own units (log10 on log axes)."""
        x, y = position
        x = math.log10(x) if graph.x_axis.log and x > 0 else x
        y = math.log10(y) if graph.y_axis.log and y > 0 else y
        return x, y

    def _review_annotations(self, graph: GraphDocument) -> None:
        """Report annotations the view will not actually show.

        Annotations are added with ``ignoreBounds=True`` so they never stretch
        the axes, and a ViewBox clips its children.  An annotation placed
        outside the plotted range is therefore built correctly, added to the
        scene correctly, and still invisible -- which is the single most
        confusing way for this to fail, because every check short of looking
        at the pixels says the annotation is present.
        """
        if not self._annotation_items:
            return
        (x_low, x_high), (y_low, y_high) = self.getPlotItem().vb.viewRange()
        log.debug(
            "annotation review: view x=[%.6g, %.6g] y=[%.6g, %.6g] (plot units%s)",
            x_low,
            x_high,
            y_low,
            y_high,
            ", log10" if graph.x_axis.log or graph.y_axis.log else "",
        )
        for annotation, item in self._annotation_items:
            if not isinstance(item, (pg.TextItem, pg.InfiniteLine, pg.PlotCurveItem)):
                continue  # the arrow head shares its annotation with the shaft
            x, y = self._plot_position(graph, annotation.position)
            label = annotation.text or annotation.kind.value
            # A horizontal rule spans every x, a vertical rule every y.
            needs_x = annotation.kind is not AnnotationKind.HLINE
            needs_y = annotation.kind is not AnnotationKind.VLINE
            outside = []
            if needs_x and not x_low <= x <= x_high:
                outside.append(f"x={annotation.position[0]:g}")
            if needs_y and not y_low <= y <= y_high:
                outside.append(f"y={annotation.position[1]:g}")
            log.debug(
                "annotation %s kind=%s data=%s plot=(%.6g, %.6g) outside=%s",
                annotation.id,
                annotation.kind.value,
                annotation.position,
                x,
                y,
                outside or "no",
            )
            if outside:
                message = (
                    f"Annotation {label!r} is outside the plotted range "
                    f"({', '.join(outside)}); it is drawn but nothing is visible"
                )
                log.warning(message)
                self.render_warnings.append(message)
                continue
            if isinstance(item, pg.TextItem):
                self._fit_text_inside(item, label, x_high, y_high)
            log.debug("annotation %r drawn at (%.6g, %.6g)", label, x, y)

    def _fit_text_inside(
        self, item: pg.TextItem, label: str, x_high: float, y_high: float
    ) -> None:
        """Flip a label's anchor so the ViewBox does not clip it away.

        The default anchor draws text up and to the right of its point, so a
        label placed at the right or top edge of the data is clipped to
        nothing even though its anchor point is inside the plot.
        """
        bounds = item.mapRectToView(item.boundingRect())
        # View coordinates run upwards, so compare against both edges rather
        # than assuming which of top/bottom is numerically larger.
        text_right = max(bounds.left(), bounds.right())
        text_top = max(bounds.top(), bounds.bottom())
        anchor_x = 1.0 if text_right > x_high else 0.0
        anchor_y = 0.0 if text_top > y_high else 1.0
        if (anchor_x, anchor_y) == (0.0, 1.0):
            return
        item.setAnchor(pg.Point(anchor_x, anchor_y))
        log.debug(
            "annotation %r re-anchored to (%g, %g): its text ran past the plot edge",
            label,
            anchor_x,
            anchor_y,
        )

    def _apply_ranges(self, graph: GraphDocument) -> None:
        plot = self.getPlotItem()
        view_box = plot.getViewBox()
        view_box.disableAutoRange()
        x_range, y_range = self._resolved_bounds(graph)
        if not graph.x_axis.auto_range:
            x_range = None
        if not graph.y_axis.auto_range:
            y_range = None
        if x_range is not None or y_range is not None:
            view_box.setRange(xRange=x_range, yRange=y_range, padding=0.02)
        if not graph.x_axis.auto_range and graph.x_axis.minimum is not None and graph.x_axis.maximum is not None:
            low, high = graph.x_axis.minimum, graph.x_axis.maximum
            if graph.x_axis.log and low > 0 and high > 0:
                low, high = math.log10(low), math.log10(high)
                plot.setXRange(low, high, padding=0)
            elif not graph.x_axis.log:
                plot.setXRange(low, high, padding=0)
        if not graph.y_axis.auto_range and graph.y_axis.minimum is not None and graph.y_axis.maximum is not None:
            low, high = graph.y_axis.minimum, graph.y_axis.maximum
            if graph.y_axis.log and low > 0 and high > 0:
                low, high = math.log10(low), math.log10(high)
                plot.setYRange(low, high, padding=0)
            elif not graph.y_axis.log:
                plot.setYRange(low, high, padding=0)

    def _resolved_bounds(
        self, graph: GraphDocument
    ) -> tuple[tuple[float, float] | None, tuple[float, float] | None]:
        """Bounds from complete snapshots, independent of view clipping."""
        x_values: list[np.ndarray] = []
        y_values: list[np.ndarray] = []
        for view in graph.series:
            if not view.visible or (snapshot := self._snapshots.get(view.id)) is None:
                continue
            with np.errstate(divide="ignore", invalid="ignore"):
                x = _coordinate(snapshot.x, graph.x_axis.log)
                y = _coordinate(snapshot.y, graph.y_axis.log)
            valid = np.isfinite(x) & np.isfinite(y)
            if np.any(valid):
                x_values.append(x[valid])
                y_values.append(y[valid])

        def span(values: list[np.ndarray]) -> tuple[float, float] | None:
            if not values:
                return None
            low = min(float(np.min(value)) for value in values)
            high = max(float(np.max(value)) for value in values)
            if low == high:
                padding = max(abs(low) * 0.01, 1.0)
                return (low - padding, high + padding)
            return (low, high)

        return span(x_values), span(y_values)

    def capture_preview(self, width: int = 1200) -> bytes:
        exporter = pyqtgraph.exporters.ImageExporter(self.getPlotItem())
        exporter.parameters()["width"] = width
        image = exporter.export(toBytes=True)
        data = QByteArray()
        buffer = QBuffer(data)
        buffer.open(QIODevice.OpenModeFlag.WriteOnly)
        image.save(buffer, "PNG")
        return bytes(data)

    capture_snapshot = capture_preview

    def save_image(self, path: str | Path, width: int | None = None) -> Path:
        destination = Path(path)
        if destination.suffix.lower() == ".svg":
            size = QSize(
                self._graph.width_px if self._graph else 1600,
                self._graph.height_px if self._graph else 1000,
            )
            generator = QSvgGenerator()
            generator.setFileName(str(destination))
            generator.setSize(size)
            generator.setViewBox(QRect(0, 0, size.width(), size.height()))
            generator.setResolution(self._graph.dpi if self._graph else 300)
            generator.setTitle(self._graph.title if self._graph else "Bernardyn graph")
            painter = QPainter(generator)
            try:
                self.scene().render(
                    painter,
                    QRectF(0, 0, size.width(), size.height()),
                    self.scene().sceneRect(),
                )
            finally:
                painter.end()
            return destination
        exporter = pyqtgraph.exporters.ImageExporter(self.getPlotItem())
        exporter.parameters()["width"] = width or (self._graph.width_px if self._graph else 1600)
        image = exporter.export(toBytes=True)
        dpi = self._graph.dpi if self._graph else 300
        image.setDotsPerMeterX(round(dpi / 0.0254))
        image.setDotsPerMeterY(round(dpi / 0.0254))
        image.save(str(destination))
        return destination

    def copy_to_clipboard(self) -> None:
        exporter = pyqtgraph.exporters.ImageExporter(self.getPlotItem())
        exporter.parameters()["width"] = self._graph.width_px if self._graph else 1600
        QApplication.clipboard().setImage(exporter.export(toBytes=True))

    def export_csv(self, path: str | Path) -> Path:
        destination = Path(path)
        with destination.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(["series", "x", "y", "dx", "dy"])
            for snapshot in self._snapshots.values():
                for index, (x, y) in enumerate(zip(snapshot.x, snapshot.y)):
                    writer.writerow(
                        [
                            snapshot.label,
                            f"{x:.17g}",
                            f"{y:.17g}",
                            "" if snapshot.dx is None else f"{snapshot.dx[index]:.17g}",
                            "" if snapshot.dy is None else f"{snapshot.dy[index]:.17g}",
                        ]
                    )
        return destination
