"""Public-pyIrena result discovery for saved fitting workflows.

This module uses pyIrena's result readers rather than reproducing HDF5 paths
or importing Data Explorer's GUI helpers.  The measured/model I(Q) records
stay scattering curves. Residuals and P(r) distributions are represented as
explicitly typed generic curves.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

import numpy as np

from bernardyn.core.models import CurveRole, GenericCurve, SeriesStyle
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


@dataclass(frozen=True)
class ResultCurveBundle:
    """One non-scattering scientific curve from a saved pyIrena result."""

    descriptor: ResultDescriptor
    curve: GenericCurve
    style: SeriesStyle
    graph_title: str
    x_log: bool
    y_log: bool


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


def _result(descriptor: ResultDescriptor) -> Mapping[str, Any]:
    """Load one result and supplement Sizes' stored cumulative curves.

    ``load_result`` is pyIrena's stable, high-level result interface. Its
    schema predates cumulative size distributions, so those optional stored
    arrays are obtained from pyIrena's Sizes reader without duplicating an
    HDF5 layout here.
    """
    result = dict(_reader()(descriptor.path, descriptor.analysis))
    if descriptor.analysis != "size_distribution":
        return result
    try:
        from pyirena.io.nxcansas_sizes import load_sizes_results

        sizes = load_sizes_results(descriptor.path)
    except (ImportError, KeyError, OSError, ValueError):
        return result
    for key in ("cumul_vol_dist", "cumul_num_dist", "cumul_surf_dist"):
        if result.get(key) is None:
            result[key] = sizes.get(key)
    return result


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
    result = _result(descriptor)
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


def _result_context(descriptor: ResultDescriptor, result: Mapping[str, Any]) -> tuple[str, dict[str, Any], dict[str, Any]]:
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
    return fingerprint, result_metadata, provenance


def available_curve_kinds(descriptor: ResultDescriptor) -> tuple[str, ...]:
    """Return generic curve views that have complete public-reader arrays."""
    result = _result(descriptor)
    if not result.get("found"):
        return ()
    available: list[str] = []
    if result.get("Q") is not None and result.get("residuals") is not None:
        available.append("residuals")
    if (
        descriptor.analysis == "size_distribution"
        and result.get("r_grid") is not None
        and result.get("distribution") is not None
    ):
        available.append("volume_distribution")
    if descriptor.analysis == "size_distribution" and result.get("r_grid") is not None:
        for kind, key in (
            ("cumulative_volume_distribution", "cumul_vol_dist"),
            ("cumulative_number_distribution", "cumul_num_dist"),
            ("cumulative_surface_distribution", "cumul_surf_dist"),
        ):
            if result.get(key) is not None:
                available.append(kind)
    return tuple(available)


def load_result_curve(descriptor: ResultDescriptor, kind: str) -> ResultCurveBundle:
    """Load a supported non-I(Q) curve without assigning scattering semantics."""
    result = _result(descriptor)
    if not result.get("found"):
        raise ValueError(f"{descriptor.title} is no longer available in {descriptor.path.name}")
    fingerprint, result_metadata, provenance = _result_context(descriptor, result)
    stem = descriptor.path.stem
    if kind == "residuals":
        q = _array(result, "Q")
        residuals = _array(result, "residuals", length=len(q))
        curve = GenericCurve(
            x=q,
            y=residuals,
            label=f"{stem} — {descriptor.title} residuals",
            role=CurveRole.RESIDUAL,
            x_semantic="scattering_q",
            y_semantic="normalised_residual",
            x_label="q",
            y_label="Normalised residual",
            x_unit="1/angstrom",
            y_unit="dimensionless",
            metadata={"bernardyn_result": {**result_metadata, "role": "residual"}},
            provenance=provenance,
            source_fingerprint=fingerprint,
        )
        return ResultCurveBundle(
            descriptor=descriptor,
            curve=curve,
            style=SeriesStyle(line_style="none", symbol="o"),
            graph_title=f"{descriptor.title} residuals",
            x_log=True,
            y_log=False,
        )
    if kind == "volume_distribution" and descriptor.analysis == "size_distribution":
        radii = _array(result, "r_grid")
        distribution = _array(result, "distribution", length=len(radii))
        error = result.get("distribution_std")
        curve = GenericCurve(
            x=radii,
            y=distribution,
            dy=None if error is None else _array(result, "distribution_std", length=len(radii)),
            label=f"{stem} — {descriptor.title} volume distribution",
            role=CurveRole.DISTRIBUTION,
            x_semantic="particle_radius",
            y_semantic="volume_fraction_density_per_radius",
            x_label="Radius",
            y_label="Volume fraction density",
            x_unit="angstrom",
            y_unit="1/angstrom",
            uncertainty_kind="standard_deviation" if error is not None else None,
            metadata={"bernardyn_result": {**result_metadata, "role": "volume_distribution"}},
            provenance=provenance,
            source_fingerprint=fingerprint,
        )
        return ResultCurveBundle(
            descriptor=descriptor,
            curve=curve,
            style=SeriesStyle(
                line_style="solid", symbol="o", show_error_bars=error is not None
            ),
            graph_title=f"{descriptor.title} volume distribution",
            x_log=False,
            y_log=False,
        )
    cumulative = {
        "cumulative_volume_distribution": (
            "cumul_vol_dist",
            "Cumulative volume distribution",
            "cumulative_volume_fraction",
            "Cumulative volume fraction",
            "volume_fraction",
        ),
        "cumulative_number_distribution": (
            "cumul_num_dist",
            "Cumulative number distribution",
            "cumulative_number_fraction",
            "Cumulative number fraction",
            "dimensionless",
        ),
        "cumulative_surface_distribution": (
            "cumul_surf_dist",
            "Cumulative surface distribution",
            "cumulative_specific_surface",
            "Cumulative specific surface",
            "1/angstrom",
        ),
    }
    if kind in cumulative and descriptor.analysis == "size_distribution":
        key, title, semantic, y_label, y_unit = cumulative[kind]
        radii = _array(result, "r_grid")
        curve = GenericCurve(
            x=radii,
            y=_array(result, key, length=len(radii)),
            label=f"{stem} — {descriptor.title} {title.lower()}",
            role=CurveRole.DISTRIBUTION,
            x_semantic="particle_radius",
            y_semantic=semantic,
            x_label="Radius",
            y_label=y_label,
            x_unit="angstrom",
            y_unit=y_unit,
            metadata={"bernardyn_result": {**result_metadata, "role": kind}},
            provenance=provenance,
            source_fingerprint=fingerprint,
        )
        return ResultCurveBundle(
            descriptor=descriptor,
            curve=curve,
            style=SeriesStyle(line_style="solid", symbol="o"),
            graph_title=f"{descriptor.title} {title.lower()}",
            x_log=False,
            y_log=False,
        )
    raise ValueError(f"{kind!r} is not available for {descriptor.title}")
