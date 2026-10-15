"""Plain-text exports of resolved (displayed) graph series.

CSV exports start with ``#`` comment lines (format version, graph, axes, and
one line per series with its view and units), then the column header.  Read
them with ``pandas.read_csv(path, comment="#")``, or with the standard library::

    rows = csv.DictReader(line for line in open(path) if not line.startswith("#"))

(``numpy.genfromtxt(..., names=True)`` takes the first comment line as the
header, so skip the comment lines first.)
"""

from __future__ import annotations

import csv
import os
import re
import tempfile
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import TextIO

from bernardyn import __version__
from bernardyn.core.models import GraphDocument, PlotSeries
from bernardyn.core.units import axis_label, format_unit

CSV_EXPORT_FORMAT = "bernardyn-displayed-data-csv"
CSV_EXPORT_VERSION = 1


def _write_atomically(destination: Path, newline: str | None, write: Callable[[TextIO], None]) -> Path:
    """Write a text export beside its destination, then replace it in one step.

    A failed export never leaves a truncated file in place of a good one.
    """
    handle = tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", newline=newline, prefix=f".{destination.name}.",
        suffix=".tmp", dir=destination.parent, delete=False,
    )
    temporary = Path(handle.name)
    try:
        with handle:
            write(handle)
        os.replace(temporary, destination)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
    return destination


def export_displayed_csv(
    path: str | Path,
    graph: GraphDocument,
    snapshots: Mapping[str, PlotSeries],
    *,
    include_hidden: bool = False,
    uncertainty_notes: Mapping[str, str] | None = None,
) -> Path:
    """Write the displayed (transformed, masked) points of each series as CSV.

    The values are exactly those plotted: after the view transform, the
    selected source-X range, and removal of points invalid on log axes.  Axis
    display limits do not clip the export.
    """
    destination = Path(path)
    notes = uncertainty_notes or {}
    exported = [
        (view, snapshots[view.id])
        for view in graph.series
        if (include_hidden or view.visible) and view.id in snapshots
    ]

    def comment(text: str) -> str:
        return "# " + " ".join(str(text).split())

    def write(handle: TextIO) -> None:
        handle.write(comment(f"format = {CSV_EXPORT_FORMAT} v{CSV_EXPORT_VERSION}") + "\n")
        handle.write(comment(f"bernardyn = {__version__}") + "\n")
        handle.write(comment(f"graph = {graph.title}") + "\n")
        handle.write(comment(f"x_axis = {graph.x_axis.label}") + "\n")
        handle.write(comment(f"y_axis = {graph.y_axis.label}") + "\n")
        for view, snapshot in exported:
            details = [
                f"view {snapshot.transform_id} {snapshot.transform_version}",
                f"x {axis_label(snapshot.x_label, snapshot.x_unit)}",
                f"y {axis_label(snapshot.y_label, snapshot.y_unit)}",
            ]
            if view.id in notes:
                details.append(notes[view.id])
            handle.write(comment(f"series {snapshot.label} = {'; '.join(details)}") + "\n")
        writer = csv.writer(handle)
        writer.writerow(["series", "x", "y", "dx", "dy", "source_index"])
        for _view, snapshot in exported:
            for index, (x, y) in enumerate(zip(snapshot.x, snapshot.y, strict=True)):
                writer.writerow(
                    [
                        snapshot.label,
                        f"{x:.17g}",
                        f"{y:.17g}",
                        "" if snapshot.dx is None else f"{snapshot.dx[index]:.17g}",
                        "" if snapshot.dy is None else f"{snapshot.dy[index]:.17g}",
                        int(snapshot.source_indices[index]),
                    ]
                )

    return _write_atomically(destination, "", write)


def _wave_name(label: str, suffix: str, used: set[str]) -> str:
    stem = re.sub(r"[^A-Za-z0-9_]", "_", label).strip("_") or "series"
    if stem[0].isdigit():
        stem = f"w_{stem}"
    base = f"{stem[: 30 - len(suffix)]}_{suffix}"
    name = base
    counter = 2
    while name.lower() in used:
        tail = f"_{counter}"
        name = f"{base[: 31 - len(tail)]}{tail}"
        counter += 1
    used.add(name.lower())
    return name


def export_displayed_itx(
    path: str | Path,
    graph: GraphDocument,
    snapshots: Mapping[str, PlotSeries],
    *,
    include_hidden: bool = False,
    uncertainty_notes: Mapping[str, str] | None = None,
) -> Path:
    """Write resolved x/y/error arrays as an Igor Text (ITX) data file.

    ``uncertainty_notes`` maps series IDs to a description of uncertainties
    that were not measured; it is written as the note of that series' dy wave.
    """
    destination = Path(path)
    notes = uncertainty_notes or {}

    def write(handle: TextIO) -> None:
        used: set[str] = set()
        handle.write("IGOR\n")
        handle.write('#pragma TextEncoding = "UTF-8"\n')
        for view in graph.series:
            if not include_hidden and not view.visible:
                continue
            snapshot = snapshots.get(view.id)
            if snapshot is None:
                continue
            columns = [("x", snapshot.x), ("y", snapshot.y)]
            if snapshot.dx is not None:
                columns.append(("dx", snapshot.dx))
            if snapshot.dy is not None:
                columns.append(("dy", snapshot.dy))
            names = [_wave_name(snapshot.label, suffix, used) for suffix, _ in columns]
            handle.write(f"WAVES/D/O/N=({len(snapshot.x)}) {','.join(names)}\n")
            handle.write("BEGIN\n")
            for row in zip(*(values for _, values in columns), strict=True):
                handle.write("\t".join(f"{float(value):.17g}" for value in row) + "\n")
            handle.write("END\n")
            escaped_label = snapshot.label.replace('"', "'")
            handle.write(f'X Note {names[1]}, "Bernardyn series: {escaped_label}"\n')
            # Data units (SetScale d); dx shares X's unit and dy shares Y's.
            units = {"x": snapshot.x_unit, "dx": snapshot.x_unit, "y": snapshot.y_unit, "dy": snapshot.y_unit}
            for (suffix, _), name in zip(columns, names, strict=True):
                unit = format_unit(units[suffix]).replace('"', "'")
                if unit:
                    handle.write(f'X SetScale d 0,0,"{unit}", {name}\n')
            if snapshot.dy is not None and view.id in notes:
                escaped_note = notes[view.id].replace('"', "'")
                handle.write(f'X Note {names[-1]}, "Bernardyn: {escaped_note}"\n')

    return _write_atomically(destination, "\n", write)
