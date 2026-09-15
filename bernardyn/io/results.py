"""Public-pyIrena result discovery for the R1 I(Q) overlay workflow.

This module intentionally consumes only ``pyirena.io.results.load_result``.
It does not reproduce HDF5 paths or import Data Explorer's GUI helpers.  The
returned records are ordinary scattering curves because the R1 acceptance set
is measured/model I(Q); residuals and distributions remain R2 work.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

import numpy as np

from bernardyn.core.models import SeriesStyle
from bernardyn.io.sources import ScatteringRecord


@dataclass(frozen=True)
class ResultDescriptor:
    """An available, public pyIrena result package in one source file."""

    path: Path
    analysis: str
    title: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "path", Path(self.path).expanduser().resolve())


@dataclass(frozen=True)
class ResultBundle:
    """Measured/model I(Q) records that must be added as one selection."""

    descriptor: ResultDescriptor
    records: tuple[ScatteringRecord, ...]
    styles: tuple[SeriesStyle, ...]
    metadata: Mapping[str, Any]


_ANALYSES = (
    ("unified_fit", "Unified Fit"),
    ("size_distribution", "Size Distribution"),
)


def _fingerprint(path: Path) -> str:
    stat = path.stat()
    value = f"{path.resolve()}:{stat.st_size}:{stat.st_mtime_ns}".encode()
    return hashlib.sha256(value).hexdigest()


def _reader():
    try:
        from pyirena.io.results import load_result
    except ImportError as exc:  # pragma: no cover - covered in dependency diagnostics
        raise RuntimeError("pyIrena 1.1+ is required to read saved results") from exc
    return load_result


def discover_results(path: str | Path) -> list[ResultDescriptor]:
    """Report only result packages pyIrena says are actually available."""
    source = Path(path).expanduser().resolve()
    if not source.is_file():
        raise FileNotFoundError(source)
    load_result = _reader()
    descriptors: list[ResultDescriptor] = []
    for analysis, title in _ANALYSES:
        result = load_result(source, analysis)
        if result.get("found"):
            descriptors.append(ResultDescriptor(source, analysis, title))
    return descriptors


def _array(result: Mapping[str, Any], key: str, *, length: int | None = None) -> np.ndarray:
    value = result.get(key)
    if value is None:
        raise ValueError(f"{key} was not stored in the selected result")
    array = np.asarray(value, dtype=float)
    if array.ndim != 1 or not len(array):
        raise ValueError(f"{key} must be a non-empty one-dimensional array")
    if length is not None and len(array) != length:
        raise ValueError(f"{key} must have {length} values, got {len(array)}")
    return array


def load_result_bundle(descriptor: ResultDescriptor) -> ResultBundle:
    """Load the explicitly selected measured/model I(Q) result pair."""
    load_result = _reader()
    result = load_result(descriptor.path, descriptor.analysis)
    if not result.get("found"):
        raise ValueError(f"{descriptor.title} is no longer available in {descriptor.path.name}")
    q = _array(result, "Q")
    data = _array(result, "intensity_data", length=len(q))
    model = _array(result, "intensity_model", length=len(q))
    uncertainty_value = result.get("intensity_error")
    uncertainty = (
        None if uncertainty_value is None else _array(result, "intensity_error", length=len(q))
    )
    fingerprint = _fingerprint(descriptor.path)
    result_metadata = {
        "analysis": descriptor.analysis,
        "title": descriptor.title,
        "timestamp": result.get("timestamp"),
        "program": result.get("program"),
        "chi_squared": result.get("chi_squared"),
        "fit_quality": result.get("fit_quality"),
    }
    provenance = {
        "source_name": descriptor.path.name,
        "source_path": str(descriptor.path),
        "adapter": "pyirena.io.results.load_result",
        "adapter_version": "1",
        "result": result_metadata,
    }
    stem = descriptor.path.stem
    records = (
        ScatteringRecord(
            q=q,
            intensity=data,
            uncertainty=uncertainty,
            label=f"{stem} — {descriptor.title} data",
            metadata={"bernardyn_result": {**result_metadata, "role": "measured"}},
            provenance=provenance,
            source_fingerprint=fingerprint,
        ),
        ScatteringRecord(
            q=q,
            intensity=model,
            label=f"{stem} — {descriptor.title} fit",
            metadata={"bernardyn_result": {**result_metadata, "role": "fit"}},
            provenance=provenance,
            source_fingerprint=fingerprint,
        ),
    )
    return ResultBundle(
        descriptor=descriptor,
        records=records,
        styles=(
            SeriesStyle(line_style="none", symbol="o", show_error_bars=uncertainty is not None),
            SeriesStyle(line_style="solid", symbol=None),
        ),
        metadata=result_metadata,
    )
