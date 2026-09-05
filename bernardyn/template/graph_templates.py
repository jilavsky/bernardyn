"""Data-free graph templates stored as human-readable JSON."""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any

from bernardyn.core.models import GraphDocument, SeriesStyle, SeriesView, json_value

TEMPLATE_FORMAT = "BERNARDYN_GRAPH_TEMPLATE"
TEMPLATE_VERSION = 1


def template_document(graph: GraphDocument, name: str) -> dict[str, Any]:
    document = graph.to_dict()
    styles = [json_value(asdict(series.style)) for series in graph.series]
    transform_id = graph.series[0].transform_id if graph.series else "raw"
    transform_parameters = (
        json_value(graph.series[0].transform_parameters) if graph.series else {}
    )
    document["series"] = []
    return {
        "format": TEMPLATE_FORMAT,
        "schema_version": TEMPLATE_VERSION,
        "name": name,
        "graph": document,
        "series_styles": styles,
        "transform_id": transform_id,
        "transform_parameters": transform_parameters,
    }


def save_template(path: str | Path, graph: GraphDocument, name: str) -> Path:
    destination = Path(path).expanduser().resolve()
    if not destination.name.endswith(".bernardyn-template.json"):
        destination = destination.with_name(destination.name + ".bernardyn-template.json")
    destination.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        prefix=f".{destination.name}.",
        suffix=".tmp",
        dir=destination.parent,
        delete=False,
    )
    temp_path = Path(handle.name)
    try:
        json.dump(template_document(graph, name), handle, indent=2, ensure_ascii=False)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
        handle.close()
        os.replace(temp_path, destination)
    except Exception:
        handle.close()
        temp_path.unlink(missing_ok=True)
        raise
    return destination


def load_template(path: str | Path) -> dict[str, Any]:
    document = json.loads(Path(path).read_text(encoding="utf-8"))
    if document.get("format") != TEMPLATE_FORMAT:
        raise ValueError("not a Bernardyn graph template")
    if int(document.get("schema_version", 0)) != TEMPLATE_VERSION:
        raise ValueError("unsupported Bernardyn template version")
    return document


def apply_template(graph: GraphDocument, document: dict[str, Any]) -> GraphDocument:
    template = GraphDocument.from_dict(document["graph"])
    styles = [
        SeriesStyle(
            **{
                **value,
                "color": tuple(value.get("color", (31, 119, 180, 255))),
                "error_color": tuple(value.get("error_color", (90, 90, 90, 180))),
            }
        )
        for value in document.get("series_styles", [])
    ]
    transform_id = str(document.get("transform_id", "raw"))
    parameters = dict(document.get("transform_parameters", {}))
    series: list[SeriesView] = []
    for index, existing in enumerate(graph.series):
        style = styles[index % len(styles)] if styles else existing.style
        series.append(
            replace(
                existing,
                style=style,
                transform_id=transform_id,
                transform_parameters=parameters,
            )
        )
    return replace(
        graph,
        title=template.title,
        renderer_id=template.renderer_id,
        series=tuple(series),
        x_axis=template.x_axis,
        y_axis=template.y_axis,
        typography=template.typography,
        legend=template.legend,
        annotations=template.annotations,
        background=template.background,
        width_px=template.width_px,
        height_px=template.height_px,
        width_in=template.width_in,
        height_in=template.height_in,
        dpi=template.dpi,
        renderer_config=template.renderer_config,
        description=template.description,
        notes=template.notes,
    )
