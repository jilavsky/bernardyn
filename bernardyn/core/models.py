"""Validated, serializable scientific and graph-domain models.

Only this layer owns plot state. Qt widgets render these objects but never
become the source of truth.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass, field, fields, replace
from enum import Enum
from typing import Any
from uuid import UUID, uuid4

import numpy as np
from numpy.typing import NDArray

FloatArray = NDArray[np.float64]
IndexArray = NDArray[np.int64]
RGBA = tuple[int, int, int, int]


def new_id() -> str:
    return str(uuid4())


def _valid_id(value: str) -> str:
    UUID(str(value))
    return str(value)


def _array(value: Any, *, name: str, length: int | None = None) -> FloatArray:
    result = np.array(value, dtype=np.float64, copy=True)
    if result.ndim != 1:
        raise ValueError(f"{name} must be a one-dimensional array")
    if length is not None and len(result) != length:
        raise ValueError(f"{name} must contain {length} values, got {len(result)}")
    result.setflags(write=False)
    return result


def json_value(value: Any) -> Any:
    """Convert model values to JSON-compatible built-in types."""
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Mapping):
        return {str(key): json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_value(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def split_known_fields(kind: type, value: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Split a JSON object into this dataclass's fields and unknown extras.

    Unknown keys come from a newer Bernardyn.  They are returned separately so
    the caller can keep them in ``extras`` rather than failing with a
    ``TypeError`` or silently dropping them on the next save.  A literal
    ``extras`` key is never accepted from a file.
    """
    names = {item.name for item in fields(kind)} - {"extras"}
    known = {key: item for key, item in value.items() if key in names}
    extras = {key: item for key, item in value.items() if key not in names and key != "extras"}
    return known, extras


def merge_extras(model: Any, document: dict[str, Any]) -> dict[str, Any]:
    """Write preserved unknown fields back beside the known ones.

    Extras never override a known field, and the ``extras`` key itself is not
    written, so a file without unknown fields is unchanged for older readers.
    """
    result = {key: item for key, item in document.items() if key != "extras"}
    for key, item in getattr(model, "extras", {}).items():
        result.setdefault(key, json_value(item))
    return result


# WARNING -- these are ``str``-based enums, and that has one sharp edge.
#
# Qt stores widget item data as a QVariant, and a str subclass is convertible
# to QString, so Qt converts it.  Put a member in and a plain str comes back:
#
#     combo.addItem("Text", AnnotationKind.TEXT)
#     combo.currentData()          # -> 'text', a str, NOT AnnotationKind.TEXT
#
# Equality still holds ('text' == AnnotationKind.TEXT), so this hides well.
# Identity does not, and `is` against an enum member is the natural thing to
# write.  That combination silently broke every annotation added through the
# Add button: the renderer's `kind is AnnotationKind.TEXT` chain matched no
# branch, drew nothing, and raised nothing, while the annotation sat in the
# document looking perfectly correct.  A saved-and-reloaded graph worked,
# because from_dict() reconstructs the member -- which made it look like a
# rendering bug rather than a data one.
#
# Rules, so this cannot come back:
#   * Every dataclass below coerces its own kind field in __post_init__.
#     Construct these types with anything str-like and get a real member back.
#   * Anything reading kind out of a Qt widget converts explicitly:
#     AnnotationKind(combo.currentData()), never the bare value.
#   * Prefer storing plain `.value` strings in Qt item data, since that is
#     what Qt keeps regardless.
class DatasetKind(str, Enum):
    CURVE_1D = "curve_1d"
    IMAGE_2D = "image_2d"


class CurveRole(str, Enum):
    """Scientific meaning of a non-scattering one-dimensional curve."""

    RESIDUAL = "residual"
    DISTRIBUTION = "distribution"


class AnnotationKind(str, Enum):
    TEXT = "text"
    ARROW = "arrow"
    HLINE = "horizontal_line"
    VLINE = "vertical_line"
    BOX = "box"
    POWER_LAW = "power_law"


@dataclass(frozen=True)
class Dataset:
    q: FloatArray
    intensity: FloatArray
    uncertainty: FloatArray | None = None
    dq: FloatArray | None = None
    id: str = field(default_factory=new_id)
    kind: DatasetKind = DatasetKind.CURVE_1D
    label: str = "Dataset"
    q_unit: str = "1/angstrom"
    intensity_unit: str = "1/cm"
    metadata: Mapping[str, Any] = field(default_factory=dict)
    provenance: Mapping[str, Any] = field(default_factory=dict)
    source_fingerprint: str | None = None
    # Metadata keys written by a newer Bernardyn; kept and written back.
    extras: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", _valid_id(self.id))
        # See the warning above DatasetKind: coerce so `is` comparisons hold.
        object.__setattr__(self, "kind", DatasetKind(self.kind))
        q = _array(self.q, name="q")
        if not len(q):
            raise ValueError("dataset arrays cannot be empty")
        intensity = _array(self.intensity, name="intensity", length=len(q))
        uncertainty = (
            None
            if self.uncertainty is None
            else _array(self.uncertainty, name="uncertainty", length=len(q))
        )
        dq = None if self.dq is None else _array(self.dq, name="dq", length=len(q))
        object.__setattr__(self, "q", q)
        object.__setattr__(self, "intensity", intensity)
        object.__setattr__(self, "uncertainty", uncertainty)
        object.__setattr__(self, "dq", dq)
        object.__setattr__(self, "metadata", dict(self.metadata))
        object.__setattr__(self, "provenance", dict(self.provenance))

    def metadata_dict(self) -> dict[str, Any]:
        document = {
            "canonical_type": "scattering_curve_v1",
            "id": self.id,
            "kind": self.kind.value,
            "label": self.label,
            "q_unit": self.q_unit,
            "intensity_unit": self.intensity_unit,
            "metadata": json_value(self.metadata),
            "provenance": json_value(self.provenance),
            "source_fingerprint": self.source_fingerprint,
        }
        return merge_extras(self, document)

    @property
    def point_count(self) -> int:
        return len(self.q)


@dataclass(frozen=True)
class GenericCurve:
    """A typed X/Y scientific curve that is not necessarily scattering data.

    Generic curves deliberately carry semantic identifiers and display units
    instead of borrowing ``q``/``intensity`` names.  That prevents residuals,
    radius distributions, and future result types from being transformed as
    I(Q) by accident.
    """

    x: FloatArray
    y: FloatArray
    dx: FloatArray | None = None
    dy: FloatArray | None = None
    id: str = field(default_factory=new_id)
    label: str = "Curve"
    role: CurveRole = CurveRole.DISTRIBUTION
    x_semantic: str = "generic_x"
    y_semantic: str = "generic_y"
    x_label: str = "X"
    y_label: str = "Y"
    x_unit: str = ""
    y_unit: str = ""
    uncertainty_kind: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)
    provenance: Mapping[str, Any] = field(default_factory=dict)
    source_fingerprint: str | None = None
    # Metadata keys written by a newer Bernardyn; kept and written back.
    extras: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", _valid_id(self.id))
        object.__setattr__(self, "role", CurveRole(self.role))
        x = _array(self.x, name="x")
        if not len(x):
            raise ValueError("generic curve arrays cannot be empty")
        y = _array(self.y, name="y", length=len(x))
        dx = None if self.dx is None else _array(self.dx, name="dx", length=len(x))
        dy = None if self.dy is None else _array(self.dy, name="dy", length=len(x))
        if not self.x_semantic or not self.y_semantic:
            raise ValueError("generic curves require X and Y semantic identifiers")
        object.__setattr__(self, "x", x)
        object.__setattr__(self, "y", y)
        object.__setattr__(self, "dx", dx)
        object.__setattr__(self, "dy", dy)
        object.__setattr__(self, "metadata", dict(self.metadata))
        object.__setattr__(self, "provenance", dict(self.provenance))

    def metadata_dict(self) -> dict[str, Any]:
        document = {
            "canonical_type": "generic_curve_v2",
            "id": self.id,
            "label": self.label,
            "role": self.role.value,
            "x_semantic": self.x_semantic,
            "y_semantic": self.y_semantic,
            "x_label": self.x_label,
            "y_label": self.y_label,
            "x_unit": self.x_unit,
            "y_unit": self.y_unit,
            "uncertainty_kind": self.uncertainty_kind,
            "metadata": json_value(self.metadata),
            "provenance": json_value(self.provenance),
            "source_fingerprint": self.source_fingerprint,
        }
        return merge_extras(self, document)

    @property
    def point_count(self) -> int:
        return len(self.x)


@dataclass(frozen=True)
class SeriesStyle:
    color: RGBA = (31, 119, 180, 255)
    line_style: str = "solid"
    line_width: float = 1.5
    symbol: str | None = "o"
    symbol_size: float = 6.0
    opacity: float = 1.0
    show_error_bars: bool = False
    show_x_error_bars: bool = True
    show_y_error_bars: bool = True
    error_caps: bool = False
    error_cap_size: float = 0.5
    error_color: RGBA = (90, 90, 90, 180)
    error_width: float = 1.0
    # Fields written by a newer Bernardyn that this version does not know.
    # They are kept, and written back unchanged, so an older reader never
    # strips a newer reader's settings.  See ``split_known_fields``.
    extras: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for color in (self.color, self.error_color):
            if len(color) != 4 or any(not 0 <= int(channel) <= 255 for channel in color):
                raise ValueError("colors must be RGBA values between 0 and 255")
        if (
            self.line_width < 0
            or self.symbol_size < 0
            or self.error_cap_size < 0
            or not 0 <= self.opacity <= 1
        ):
            raise ValueError("invalid series style dimensions or opacity")


@dataclass(frozen=True)
class SeriesView:
    dataset_id: str
    id: str = field(default_factory=new_id)
    transform_id: str = "raw"
    transform_parameters: Mapping[str, float] = field(default_factory=dict)
    q_range: tuple[float | None, float | None] = (None, None)
    multiplier: float = 1.0
    offset: float = 0.0
    visible: bool = True
    legend_label: str | None = None
    style: SeriesStyle = field(default_factory=SeriesStyle)
    # Fields written by a newer Bernardyn that this version does not know.
    # They are kept, and written back unchanged, so an older reader never
    # strips a newer reader's settings.  See ``split_known_fields``.
    extras: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", _valid_id(self.id))
        object.__setattr__(self, "dataset_id", _valid_id(self.dataset_id))
        object.__setattr__(self, "transform_parameters", dict(self.transform_parameters))
        low, high = self.q_range
        if low is not None and high is not None and low > high:
            raise ValueError("q_range minimum cannot exceed maximum")


@dataclass(frozen=True)
class AxisSpec:
    label: str = ""
    log: bool = False
    minimum: float | None = None
    maximum: float | None = None
    auto_range: bool = True
    grid_major: bool = True
    grid_minor: bool = False
    minor_tick_labels: bool = False
    color: RGBA = (30, 30, 30, 255)
    thickness: float = 1.0
    # Fields written by a newer Bernardyn that this version does not know.
    # They are kept, and written back unchanged, so an older reader never
    # strips a newer reader's settings.  See ``split_known_fields``.
    extras: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.minimum is not None and self.maximum is not None and self.minimum >= self.maximum:
            raise ValueError("axis minimum must be less than maximum")


@dataclass(frozen=True)
class TypographySpec:
    family: str = "Arial"
    title_size: int = 14
    axis_label_size: int = 12
    tick_size: int = 10
    legend_size: int = 10
    # Fields written by a newer Bernardyn that this version does not know.
    # They are kept, and written back unchanged, so an older reader never
    # strips a newer reader's settings.  See ``split_known_fields``.
    extras: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class LegendSpec:
    visible: bool = True
    position: str = "top-right"
    framed: bool = True
    columns: int = 1
    symbol_size: float = 8.0
    # Fields written by a newer Bernardyn that this version does not know.
    # They are kept, and written back unchanged, so an older reader never
    # strips a newer reader's settings.  See ``split_known_fields``.
    extras: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.columns < 1:
            raise ValueError("legend columns must be at least one")
        if self.symbol_size <= 0:
            raise ValueError("legend symbol size must be positive")


@dataclass(frozen=True)
class Annotation:
    kind: AnnotationKind
    position: tuple[float, float]
    id: str = field(default_factory=new_id)
    end: tuple[float, float] | None = None
    text: str = ""
    color: RGBA = (20, 20, 20, 255)
    line_width: float = 1.5
    font_size: int = 11
    z_order: int = 10
    # A positive P represents the conventional SAXS slope I = B * q^-P.
    # It is used only by POWER_LAW annotations; the line's amplitude is
    # derived from ``position`` so that a guide can be repositioned directly.
    slope: float | None = None
    # Fields written by a newer Bernardyn that this version does not know.
    # They are kept, and written back unchanged, so an older reader never
    # strips a newer reader's settings.  See ``split_known_fields``.
    extras: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", _valid_id(self.id))
        # See the warning above AnnotationKind.  Coercing here, at the single
        # boundary every annotation passes through, is what lets the renderer
        # rely on `kind` being a real member and compare it with `is`.
        object.__setattr__(self, "kind", AnnotationKind(self.kind))
        if self.kind in (AnnotationKind.ARROW, AnnotationKind.BOX) and self.end is None:
            raise ValueError(f"{self.kind.value} annotations require an end point")
        if self.kind is AnnotationKind.POWER_LAW:
            # Direct construction is also used by importers and older
            # plugins, so retain a conventional P=4 default at that boundary.
            if self.slope is None:
                object.__setattr__(self, "slope", 4.0)
            if not math.isfinite(self.slope):
                raise ValueError("power-law annotations require a finite exponent")


@dataclass(frozen=True)
class GraphDocument:
    id: str = field(default_factory=new_id)
    title: str = "Scattering plot"
    renderer_id: str = "plot2d"
    # This is graph-level intent, rather than an inference from whichever
    # series happened to be added first.  Series retain their own resolved
    # parameters because values such as I0 and Rg are sample-specific.
    view_transform_id: str = "raw"
    series: tuple[SeriesView, ...] = ()
    x_axis: AxisSpec = field(default_factory=lambda: AxisSpec(label="q [Å⁻¹]", log=True))
    y_axis: AxisSpec = field(default_factory=lambda: AxisSpec(label="Intensity [cm⁻¹]", log=True))
    typography: TypographySpec = field(default_factory=TypographySpec)
    legend: LegendSpec = field(default_factory=LegendSpec)
    box_axes: bool = False
    annotations: tuple[Annotation, ...] = ()
    background: RGBA = (255, 255, 255, 255)
    background_scope: str = "canvas"
    width_px: int = 1950
    height_px: int = 1350
    width_in: float = 6.5
    height_in: float = 4.5
    dpi: int = 300
    renderer_config: Mapping[str, Any] = field(
        default_factory=lambda: {"renderer_version": "1.0"}
    )
    description: str = ""
    notes: str = ""
    # Fields written by a newer Bernardyn that this version does not know.
    # They are kept, and written back unchanged, so an older reader never
    # strips a newer reader's settings.  See ``split_known_fields``.
    extras: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", _valid_id(self.id))
        object.__setattr__(self, "series", tuple(self.series))
        object.__setattr__(self, "annotations", tuple(self.annotations))
        object.__setattr__(self, "renderer_config", dict(self.renderer_config))
        if self.background_scope not in {"canvas", "plot"}:
            raise ValueError("background scope must be 'canvas' or 'plot'")
        if self.width_px < 100 or self.height_px < 100:
            raise ValueError("graph dimensions must be at least 100 pixels")
        if self.width_in <= 0 or self.height_in <= 0 or self.dpi <= 0:
            raise ValueError("physical graph dimensions and DPI must be positive")

    def to_dict(self) -> dict[str, Any]:
        document = merge_extras(self, json_value(asdict(self)))
        for axis in ("x_axis", "y_axis"):
            document[axis] = merge_extras(getattr(self, axis), document[axis])
        document["typography"] = merge_extras(self.typography, document["typography"])
        document["legend"] = merge_extras(self.legend, document["legend"])
        document["series"] = [
            {**merge_extras(series, item), "style": merge_extras(series.style, item["style"])}
            for series, item in zip(self.series, document["series"], strict=True)
        ]
        document["annotations"] = [
            merge_extras(annotation, item)
            for annotation, item in zip(self.annotations, document["annotations"], strict=True)
        ]
        return document

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> GraphDocument:
        """Build a graph from its JSON form, keeping fields from newer writers."""

        def style(item: Mapping[str, Any]) -> SeriesStyle:
            known, extras = split_known_fields(SeriesStyle, item)
            for name, default in (("color", (31, 119, 180, 255)), ("error_color", (90, 90, 90, 180))):
                known[name] = tuple(known.get(name, default))
            return SeriesStyle(**known, extras=extras)

        def series_view(item: Mapping[str, Any]) -> SeriesView:
            known, extras = split_known_fields(SeriesView, item)
            known["style"] = style(known.get("style", {}))
            known["q_range"] = tuple(known.get("q_range", (None, None)))
            return SeriesView(**known, extras=extras)

        def annotation(item: Mapping[str, Any]) -> Annotation:
            known, extras = split_known_fields(Annotation, item)
            known["kind"] = AnnotationKind(known["kind"])
            known["position"] = tuple(known["position"])
            known["end"] = tuple(known["end"]) if known.get("end") is not None else None
            known["color"] = tuple(known.get("color", (20, 20, 20, 255)))
            return Annotation(**known, extras=extras)

        def axis(item: Mapping[str, Any]) -> AxisSpec:
            known, extras = split_known_fields(AxisSpec, item)
            if "color" in known:
                known["color"] = tuple(known["color"])
            return AxisSpec(**known, extras=extras)

        def simple(kind: type, item: Mapping[str, Any]) -> Any:
            known, extras = split_known_fields(kind, item)
            return kind(**known, extras=extras)

        series = tuple(series_view(item) for item in value.get("series", []))
        annotations = tuple(annotation(item) for item in value.get("annotations", []))
        inherited_view = (
            series[0].transform_id
            if series and all(item.transform_id == series[0].transform_id for item in series)
            else "raw"
        )
        _, extras = split_known_fields(cls, value)
        return cls(
            id=str(value["id"]),
            title=str(value.get("title", "Scattering plot")),
            renderer_id=str(value.get("renderer_id", "plot2d")),
            view_transform_id=str(value.get("view_transform_id", inherited_view)),
            series=series,
            x_axis=axis(value.get("x_axis", {})),
            y_axis=axis(value.get("y_axis", {})),
            typography=simple(TypographySpec, value.get("typography", {})),
            legend=simple(LegendSpec, value.get("legend", {})),
            box_axes=bool(value.get("box_axes", False)),
            annotations=annotations,
            background=tuple(value.get("background", (255, 255, 255, 255))),
            background_scope=str(value.get("background_scope", "canvas")),
            width_px=int(value.get("width_px", 1950)),
            height_px=int(value.get("height_px", 1350)),
            width_in=float(value.get("width_in", 6.5)),
            height_in=float(value.get("height_in", 4.5)),
            dpi=int(value.get("dpi", 300)),
            renderer_config=value.get("renderer_config", {}),
            description=str(value.get("description", "")),
            notes=str(value.get("notes", "")),
            extras=extras,
        )

    def replace_series(self, series: Iterable[SeriesView]) -> GraphDocument:
        return replace(self, series=tuple(series))


@dataclass(frozen=True)
class PlotSeries:
    series_id: str
    dataset_id: str
    x: FloatArray
    y: FloatArray
    dx: FloatArray | None = None
    dy: FloatArray | None = None
    source_indices: IndexArray | None = None
    label: str = ""
    x_label: str = ""
    y_label: str = ""
    x_unit: str = ""
    y_unit: str = ""
    transform_id: str = "raw"
    transform_version: str = "1.0"
    warnings: tuple[str, ...] = ()
    archived: bool = False

    def __post_init__(self) -> None:
        x = _array(self.x, name="x")
        y = _array(self.y, name="y", length=len(x))
        dx = None if self.dx is None else _array(self.dx, name="dx", length=len(x))
        dy = None if self.dy is None else _array(self.dy, name="dy", length=len(x))
        indices = (
            np.arange(len(x), dtype=np.int64)
            if self.source_indices is None
            else np.array(self.source_indices, dtype=np.int64, copy=True)
        )
        if indices.ndim != 1 or len(indices) != len(x):
            raise ValueError("source_indices must match plot-series length")
        indices.setflags(write=False)
        object.__setattr__(self, "x", x)
        object.__setattr__(self, "y", y)
        object.__setattr__(self, "dx", dx)
        object.__setattr__(self, "dy", dy)
        object.__setattr__(self, "source_indices", indices)
        object.__setattr__(self, "warnings", tuple(self.warnings))


@dataclass
class Workspace:
    id: str = field(default_factory=new_id)
    title: str = "Untitled workspace"
    description: str = ""
    datasets: dict[str, Dataset | GenericCurve] = field(default_factory=dict)
    graphs: list[GraphDocument] = field(default_factory=list)
    active_graph_id: str | None = None
    layout_state: str | None = None
    dirty: bool = False

    def __post_init__(self) -> None:
        self.id = _valid_id(self.id)
        self.validate()

    def validate(self) -> None:
        for key, dataset in self.datasets.items():
            if key != dataset.id:
                raise ValueError("dataset mapping key does not match dataset id")
        graph_ids = {graph.id for graph in self.graphs}
        if len(graph_ids) != len(self.graphs):
            raise ValueError("workspace graph ids must be unique")
        for graph in self.graphs:
            for series in graph.series:
                if series.dataset_id not in self.datasets:
                    raise ValueError(f"graph references missing dataset {series.dataset_id}")
        if self.active_graph_id is not None and self.active_graph_id not in graph_ids:
            raise ValueError("active graph is not present in workspace")

    def graph(self, graph_id: str) -> GraphDocument:
        for graph in self.graphs:
            if graph.id == graph_id:
                return graph
        raise KeyError(graph_id)

    def replace_graph(self, graph: GraphDocument) -> None:
        for index, existing in enumerate(self.graphs):
            if existing.id == graph.id:
                self.graphs[index] = graph
                self.dirty = True
                self.validate()
                return
        raise KeyError(graph.id)

    def add_dataset(self, dataset: Dataset | GenericCurve) -> None:
        self.datasets[dataset.id] = dataset
        self.dirty = True

    def add_graph(self, graph: GraphDocument) -> None:
        if any(existing.id == graph.id for existing in self.graphs):
            raise ValueError(f"duplicate graph id {graph.id}")
        for series in graph.series:
            if series.dataset_id not in self.datasets:
                raise ValueError(f"graph references missing dataset {series.dataset_id}")
        self.graphs.append(graph)
        self.active_graph_id = graph.id
        self.dirty = True
