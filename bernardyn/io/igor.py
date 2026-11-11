"""Igor-compatible data export, intentionally separate from graph packages."""

from __future__ import annotations

import os
import tempfile
from collections.abc import Iterable
from pathlib import Path

from bernardyn.core.models import Dataset, Workspace


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
    # Check before touching the file system: an export that has nothing to
    # write must never replace (or truncate) an existing experiment.
    scattering = [
        dataset
        for dataset_id in selected
        if isinstance(dataset := workspace.datasets[dataset_id], Dataset)
    ]
    if not scattering:
        raise ValueError("Igor h5xp export requires at least one scattering I(Q) dataset")
    # Write beside the destination and replace it in one step, as the CSV and
    # ITX exports do, so a failure part-way leaves the old file intact.
    handle_file = tempfile.NamedTemporaryFile(
        prefix=f".{destination.stem}.", suffix=".h5xp", dir=destination.parent, delete=False
    )
    temporary = Path(handle_file.name)
    handle_file.close()
    try:
        with create_h5xp(temporary, overwrite=True) as handle:
            used: set[str] = set()
            for dataset in scattering:
                base = "".join(
                    char if char.isalnum() or char == "_" else "_" for char in dataset.label
                )
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
                        "UncertaintyKind": dataset.uncertainty_kind or "not recorded",
                    },
                )
        os.replace(temporary, destination)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
    return destination
