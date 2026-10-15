"""Data-free graph templates stored as human-readable JSON."""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any

from bernardyn.core.models import (
    GraphDocument,
    SeriesStyle,
    SeriesView,
    json_value,
    merge_extras,
    split_known_fields,
)

TEMPLATE_FORMAT = "BERNARDYN_GRAPH_TEMPLATE"
TEMPLATE_VERSION = 1


def template_document(graph: GraphDocument, name: str) -> dict[str, Any]:
    document = graph.to_dict()
    styles = [merge_extras(series.style, json_value(asdict(series.style))) for series in graph.series]
    transform_id = graph.view_transform_id
    document["series"] = []
    return {
        "format": TEMPLATE_FORMAT,
        "schema_version": TEMPLATE_VERSION,
        "name": name,
        "graph": document,
        "series_styles": styles,
        "transform_id": transform_id,
    }


TEMPLATE_SUFFIX = ".bernardyn-template.json"


def template_file_name(name: str) -> str:
    """Return the file name a template called ``name`` is stored under."""
    safe = "".join(char if char.isalnum() or char in "-_ " else "_" for char in name).strip()
    return f"{safe or 'template'}{TEMPLATE_SUFFIX}"


def _write_document(path: str | Path, document: dict[str, Any]) -> Path:
    destination = Path(path).expanduser().resolve()
    if not destination.name.endswith(TEMPLATE_SUFFIX):
        destination = destination.with_name(destination.name + TEMPLATE_SUFFIX)
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
        json.dump(document, handle, indent=2, ensure_ascii=False)
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


def save_template(path: str | Path, graph: GraphDocument, name: str) -> Path:
    return _write_document(path, template_document(graph, name))


def rename_template(path: str | Path, new_name: str) -> Path:
    """Rename a stored template, moving it to the file name for ``new_name``.

    Raises FileExistsError if a different template already uses that file.
    """
    source = Path(path).expanduser().resolve()
    name = new_name.strip()
    if not name:
        raise ValueError("a template name cannot be empty")
    document = load_template(source)
    destination = source.with_name(template_file_name(name))
    if destination != source and destination.exists():
        raise FileExistsError(f"a template is already saved as {destination.name}")
    document["name"] = name
    written = _write_document(destination, document)
    if written != source:
        source.unlink()
    return written


def template_summary(document: dict[str, Any]) -> str:
    """One line describing what applying a template changes."""
    graph = document.get("graph", {})
    view = str(document.get("transform_id", "raw"))
    parts = [
        "General I(Q) view" if view == "raw" else f"{view.replace('_', ' ').capitalize()} view",
        f"{graph.get('width_px', '?')}×{graph.get('height_px', '?')} px at {graph.get('dpi', '?')} dpi",
    ]
    styles = len(document.get("series_styles", []))
    if styles:
        parts.append(f"{styles} series style{'s' if styles != 1 else ''}")
    if graph.get("box_axes"):
        parts.append("boxed axes")
    return " · ".join(parts)


def load_template(path: str | Path) -> dict[str, Any]:
    document = json.loads(Path(path).read_text(encoding="utf-8"))
    if document.get("format") != TEMPLATE_FORMAT:
        raise ValueError("not a Bernardyn graph template")
    if int(document.get("schema_version", 0)) != TEMPLATE_VERSION:
        raise ValueError("unsupported Bernardyn template version")
    return document


def apply_template(graph: GraphDocument, document: dict[str, Any]) -> GraphDocument:
    template = GraphDocument.from_dict(document["graph"])
    styles = []
    for value in document.get("series_styles", []):
        known, extras = split_known_fields(SeriesStyle, value)
        known["color"] = tuple(known.get("color", (31, 119, 180, 255)))
        known["error_color"] = tuple(known.get("error_color", (90, 90, 90, 180)))
        styles.append(SeriesStyle(**known, extras=extras))
    transform_id = str(document.get("transform_id", "raw"))
    series: list[SeriesView] = []
    for index, existing in enumerate(graph.series):
        style = styles[index % len(styles)] if styles else existing.style
        series.append(
            replace(
                existing,
                style=style,
                transform_id=transform_id,
                # A graph template is presentation intent, not a transfer of
                # one sample's I0/Rg (or future fit parameters) to another.
                transform_parameters=dict(existing.transform_parameters),
            )
        )
    return replace(
        graph,
        title=template.title,
        renderer_id=template.renderer_id,
        view_transform_id=transform_id,
        series=tuple(series),
        x_axis=template.x_axis,
        y_axis=template.y_axis,
        typography=template.typography,
        legend=template.legend,
        box_axes=template.box_axes,
        annotations=template.annotations,
        background=template.background,
        background_scope=template.background_scope,
        width_px=template.width_px,
        height_px=template.height_px,
        width_in=template.width_in,
        height_in=template.height_in,
        dpi=template.dpi,
        renderer_config=template.renderer_config,
        description=template.description,
        notes=template.notes,
    )
