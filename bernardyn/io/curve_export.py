"""Plain-text exports of resolved (displayed) graph series."""

from __future__ import annotations

import csv
import re
from pathlib import Path
from typing import Mapping

from bernardyn.core.models import GraphDocument, PlotSeries


def export_displayed_csv(
    path: str | Path,
    graph: GraphDocument,
    snapshots: Mapping[str, PlotSeries],
) -> Path:
    destination = Path(path)
    with destination.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["series", "x", "y", "dx", "dy", "source_index"])
        for view in graph.series:
            snapshot = snapshots.get(view.id)
            if snapshot is None:
                continue
            for index, (x, y) in enumerate(zip(snapshot.x, snapshot.y)):
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
    return destination


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
) -> Path:
    """Write resolved x/y/error arrays as an Igor Text (ITX) data file."""
    destination = Path(path)
    used: set[str] = set()
    with destination.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write("IGOR\n")
        handle.write('#pragma TextEncoding = "UTF-8"\n')
        for view in graph.series:
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
            for row in zip(*(values for _, values in columns)):
                handle.write("\t".join(f"{float(value):.17g}" for value in row) + "\n")
            handle.write("END\n")
            escaped_label = snapshot.label.replace('"', "'")
            handle.write(f'X Note {names[1]}, "Bernardyn series: {escaped_label}"\n')
    return destination
