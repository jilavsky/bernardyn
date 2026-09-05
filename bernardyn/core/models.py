"""Validated, serializable scientific and graph-domain models.

Only this layer owns plot state. Qt widgets render these objects but never
become the source of truth.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace
from enum import Enum
from typing import Any, Iterable, Mapping
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


class DatasetKind(str, Enum):
    CURVE_1D = "curve_1d"
    IMAGE_2D = "image_2d"


class AnnotationKind(str, Enum):
    TEXT = "text"
    ARROW = "arrow"
    HLINE = "horizontal_line"
    VLINE = "vertical_line"


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

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", _valid_id(self.id))
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
        return {
            "id": self.id,
            "kind": self.kind.value,
            "label": self.label,
            "q_unit": self.q_unit,
            "intensity_unit": self.intensity_unit,
            "metadata": json_value(self.metadata),
            "provenance": json_value(self.provenance),
            "source_fingerprint": self.source_fingerprint,
        }


@dataclass(frozen=True)
class SeriesStyle:
    color: RGBA = (31, 119, 180, 255)
    line_style: str = "solid"
    line_width: float = 1.5
    symbol: str | None = "o"
    symbol_size: float = 6.0
    opacity: float = 1.0
    show_error_bars: bool = False
    error_color: RGBA = (90, 90, 90, 180)
    error_width: float = 1.0

    def __post_init__(self) -> None:
        for color in (self.color, self.error_color):
            if len(color) != 4 or any(not 0 <= int(channel) <= 255 for channel in color):
                raise ValueError("colors must be RGBA values between 0 and 255")
        if self.line_width < 0 or self.symbol_size < 0 or not 0 <= self.opacity <= 1:
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
    color: RGBA = (30, 30, 30, 255)
    thickness: float = 1.0

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


@dataclass(frozen=True)
class LegendSpec:
    visible: bool = True
    position: str = "top-right"
    framed: bool = True
    columns: int = 1


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

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", _valid_id(self.id))
        if self.kind is AnnotationKind.ARROW and self.end is None:
            raise ValueError("arrow annotations require an end point")


@dataclass(frozen=True)
class GraphDocument:
    id: str = field(default_factory=new_id)
    title: str = "Scattering plot"
    renderer_id: str = "plot2d"
    series: tuple[SeriesView, ...] = ()
    x_axis: AxisSpec = field(default_factory=lambda: AxisSpec(label="q [Å⁻¹]", log=True))
    y_axis: AxisSpec = field(default_factory=lambda: AxisSpec(label="Intensity [cm⁻¹]", log=True))
    typography: TypographySpec = field(default_factory=TypographySpec)
    legend: LegendSpec = field(default_factory=LegendSpec)
    annotations: tuple[Annotation, ...] = ()
    background: RGBA = (255, 255, 255, 255)
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

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", _valid_id(self.id))
        object.__setattr__(self, "series", tuple(self.series))
        object.__setattr__(self, "annotations", tuple(self.annotations))
        object.__setattr__(self, "renderer_config", dict(self.renderer_config))
        if self.width_px < 100 or self.height_px < 100:
            raise ValueError("graph dimensions must be at least 100 pixels")
        if self.width_in <= 0 or self.height_in <= 0 or self.dpi <= 0:
            raise ValueError("physical graph dimensions and DPI must be positive")

    def to_dict(self) -> dict[str, Any]:
        return json_value(asdict(self))

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "GraphDocument":
        series = tuple(
            SeriesView(
                **{
                    **item,
                    "style": SeriesStyle(
                        **{
                            **item.get("style", {}),
                            "color": tuple(item.get("style", {}).get("color", (31, 119, 180, 255))),
                            "error_color": tuple(
                                item.get("style", {}).get("error_color", (90, 90, 90, 180))
                            ),
                        }
                    ),
                    "q_range": tuple(item.get("q_range", (None, None))),
                }
            )
            for item in value.get("series", [])
        )
        annotations = tuple(
            Annotation(
                **{
                    **item,
                    "kind": AnnotationKind(item["kind"]),
                    "position": tuple(item["position"]),
                    "end": tuple(item["end"]) if item.get("end") is not None else None,
                    "color": tuple(item.get("color", (20, 20, 20, 255))),
                }
            )
            for item in value.get("annotations", [])
        )
        x_axis = dict(value.get("x_axis", {}))
        y_axis = dict(value.get("y_axis", {}))
        if "color" in x_axis:
            x_axis["color"] = tuple(x_axis["color"])
        if "color" in y_axis:
            y_axis["color"] = tuple(y_axis["color"])
        return cls(
            id=str(value["id"]),
            title=str(value.get("title", "Scattering plot")),
            renderer_id=str(value.get("renderer_id", "plot2d")),
            series=series,
            x_axis=AxisSpec(**x_axis),
            y_axis=AxisSpec(**y_axis),
            typography=TypographySpec(**value.get("typography", {})),
            legend=LegendSpec(**value.get("legend", {})),
            annotations=annotations,
            background=tuple(value.get("background", (255, 255, 255, 255))),
            width_px=int(value.get("width_px", 1950)),
            height_px=int(value.get("height_px", 1350)),
            width_in=float(value.get("width_in", 6.5)),
            height_in=float(value.get("height_in", 4.5)),
            dpi=int(value.get("dpi", 300)),
            renderer_config=value.get("renderer_config", {}),
            description=str(value.get("description", "")),
            notes=str(value.get("notes", "")),
        )

    def replace_series(self, series: Iterable[SeriesView]) -> "GraphDocument":
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
    datasets: dict[str, Dataset] = field(default_factory=dict)
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

    def add_dataset(self, dataset: Dataset) -> None:
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
