"""Plain-text exports of resolved (displayed) graph series."""

from __future__ import annotations

import csv
import os
import re
import tempfile
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import TextIO

from bernardyn.core.models import GraphDocument, PlotSeries


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
) -> Path:
    destination = Path(path)

    def write(handle: TextIO) -> None:
        writer = csv.writer(handle)
        writer.writerow(["series", "x", "y", "dx", "dy", "source_index"])
        for view in graph.series:
            if not include_hidden and not view.visible:
                continue
            snapshot = snapshots.get(view.id)
            if snapshot is None:
                continue
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
            if snapshot.dy is not None and view.id in notes:
                escaped_note = notes[view.id].replace('"', "'")
                handle.write(f'X Note {names[-1]}, "Bernardyn: {escaped_note}"\n')

    return _write_atomically(destination, "\n", write)
