"""Bernardyn scientific plotting workbench."""

__version__ = "1.0.0"

from bernardyn.api import (
    SERIES_PRESETS,
    PlotRequest,
    PlotResult,
    PlotService,
    Presentation,
    ResultInput,
    ScatteringInput,
    create_plot,
    inspect_data,
    list_recipes,
)
from bernardyn.core.models import (
    Annotation,
    CurveRole,
    Dataset,
    DatasetKind,
    GenericCurve,
    GraphDocument,
    PlotSeries,
    SeriesView,
    Workspace,
)

__all__ = [
    "Annotation",
    "CurveRole",
    "Dataset",
    "DatasetKind",
    "GenericCurve",
    "GraphDocument",
    "PlotSeries",
    "SeriesView",
    "Workspace",
    "PlotRequest",
    "PlotResult",
    "PlotService",
    "Presentation",
    "SERIES_PRESETS",
    "ResultInput",
    "ScatteringInput",
    "create_plot",
    "inspect_data",
    "list_recipes",
]
