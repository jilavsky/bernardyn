"""Igor-compatible data export, intentionally separate from graph packages."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

from bernardyn.core.models import Workspace


def export_datasets_to_h5xp(
    path: str | Path,
    workspace: Workspace,
    dataset_ids: Iterable[str] | None = None,
) -> Path:
    try:
        from pyirena.io import create_h5xp, write_iq_data
    except ImportError as exc:
        raise RuntimeError("Igor h5xp export requires a compatible PyIrena installation") from exc

    destination = Path(path).expanduser().resolve()
    if destination.suffix.lower() != ".h5xp":
        destination = destination.with_suffix(".h5xp")
    selected = list(dataset_ids) if dataset_ids is not None else list(workspace.datasets)
    with create_h5xp(destination, overwrite=True) as handle:
        used: set[str] = set()
        for dataset_id in selected:
            dataset = workspace.datasets[dataset_id]
            base = "".join(char if char.isalnum() or char == "_" else "_" for char in dataset.label)
            name = base.strip("_") or f"dataset_{len(used) + 1}"
            original = name
            counter = 2
            while name in used:
                name = f"{original}_{counter}"
                counter += 1
            used.add(name)
            write_iq_data(
                handle,
                name,
                dataset.q,
                dataset.intensity,
                error=dataset.uncertainty,
                dq=dataset.dq,
                wave_note={
                    "BernardynDatasetUUID": dataset.id,
                    "QUnit": dataset.q_unit,
                    "IntensityUnit": dataset.intensity_unit,
                },
            )
    return destination
