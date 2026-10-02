"""Read saved pyIrena fitting curves through its schema and result readers."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

import h5py
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
    """Available I(Q) records that must be added as one selection."""

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
    ("modeling", "Modeling"),
    ("simple_fits", "Simple Fits"),
    ("waxs_peakfit", "WAXS Peak Fit"),
    ("carbon_fit", "Carbon fitting"),
)

_EXTRA_READERS = {
    "modeling": ("pyirena.io.nxcansas_modeling", "load_modeling_results"),
    "simple_fits": ("pyirena.io.nxcansas_simple_fits", "load_simple_fit_results"),
    "waxs_peakfit": ("pyirena.io.nxcansas_waxs_peakfit", "load_waxs_peakfit_results"),
    "carbon_fit": ("pyirena.io.nxcansas_carbon_fit", "load_carbon_fit_results"),
}


def _reader_id(analysis: str) -> str:
    if analysis in _EXTRA_READERS:
        module, name = _EXTRA_READERS[analysis]
        return f"{module}.{name}"
    return "pyirena.io.results.load_result"


def _fingerprint(path: Path) -> str:
    stat = path.stat()
    value = f"{path.resolve()}:{stat.st_size}:{stat.st_mtime_ns}".encode()
    return hashlib.sha256(value).hexdigest()


def _reader():
    try:
        from pyirena.io.results import load_result
    except ImportError as exc:  # pragma: no cover - covered in dependency diagnostics
        raise RuntimeError("pyIrena 1.2.0b2+ is required to read saved results") from exc
    return load_result


def _result(descriptor: ResultDescriptor) -> Mapping[str, Any]:
    """Load one result with pyIrena's readers, including all Sizes curves."""
    if descriptor.analysis in _EXTRA_READERS:
        from importlib import import_module

        module, name = _EXTRA_READERS[descriptor.analysis]
        raw = getattr(import_module(module), name)(descriptor.path)
        if raw is None:
            return {"found": False}
        result = dict(raw)
        result["found"] = True
        if descriptor.analysis == "modeling":
            result["Q"] = result.get("model_q")
            result["intensity_model"] = result.get("model_I")
        else:
            result["intensity_model"] = result.get({
                "simple_fits": "I_model",
                "waxs_peakfit": "I_fit",
                "carbon_fit": "I_model",
            }[descriptor.analysis])
        return result
    result = dict(_reader()(descriptor.path, descriptor.analysis))
    if descriptor.analysis != "size_distribution":
        return result
    try:
        from pyirena.io.nxcansas_sizes import load_sizes_results

        sizes = load_sizes_results(descriptor.path)
    except (ImportError, KeyError, OSError, ValueError):
        return result
    for key in (
        "number_dist", "surface_dist", "cumul_vol_dist", "cumul_num_dist", "cumul_surf_dist"
    ):
        if result.get(key) is None:
            result[key] = sizes.get(key)
    return result


def discover_results(path: str | Path) -> list[ResultDescriptor]:
    """Report result groups with at least one stored I(Q) curve."""
    source = Path(path).expanduser().resolve()
    if not source.is_file():
        raise FileNotFoundError(source)
    from pyirena.io.schema import TOOL_REGISTRY

    descriptors: list[ResultDescriptor] = []
    with h5py.File(source, "r") as handle:
        for analysis, title in _ANALYSES:
            schema = TOOL_REGISTRY[analysis]
            group = handle.get(schema["group"])
            if not isinstance(group, h5py.Group):
                continue
            if any(
                plot["plot_type"] == "iq"
                and isinstance(group.get(plot["x"]), h5py.Dataset)
                and isinstance(group.get(plot["y"]), h5py.Dataset)
                for plot in schema["plots"]
            ):
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
    """Load the available measured, fitted, and component I(Q) curves."""
    result = _result(descriptor)
    if not result.get("found"):
        raise ValueError(f"{descriptor.title} is no longer available in {descriptor.path.name}")
    q = _array(result, "Q")
    if result.get("intensity_data") is None and result.get("intensity_model") is None:
        raise ValueError(f"{descriptor.title} has no stored I(Q) curves")
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
        "adapter": _reader_id(descriptor.analysis),
        "adapter_version": "1",
        "result": result_metadata,
    }
    stem = descriptor.path.stem
    records: list[ScatteringRecord] = []
    styles: list[SeriesStyle] = []

    def add(
        key: str, role: str, label: str, *, x: np.ndarray = q,
        source: Mapping[str, Any] | None = None,
    ) -> None:
        values = result if source is None else source
        if values.get(key) is None:
            return
        y = _array(values, key, length=len(x))
        intensity_unit = (
            "arb" if descriptor.analysis == "waxs_peakfit" or (
                descriptor.analysis == "simple_fits" and role != "measured"
            ) else "1/cm"
        )
        records.append(ScatteringRecord(
            q=x,
            intensity=y,
            uncertainty=uncertainty if role == "measured" else None,
            intensity_unit=intensity_unit,
            label=f"{stem} — {descriptor.title} {label}",
            metadata={"bernardyn_result": {**result_metadata, "role": role}},
            provenance=provenance,
            source_fingerprint=fingerprint,
        ))
        styles.append(SeriesStyle(
            line_style="none" if role == "measured" else "solid",
            symbol="o" if role == "measured" else None,
            show_error_bars=role == "measured" and uncertainty is not None,
        ))

    add("intensity_data", "measured", "data")
    add("intensity_model", "fit", "fit")
    if descriptor.analysis == "waxs_peakfit":
        add("I_bg", "background", "background")
        for index, peak in enumerate(result.get("peak_curves") or (), 1):
            if peak.get("Q_peak") is None or peak.get("I_peak") is None:
                continue
            peak_q = np.asarray(peak["Q_peak"], dtype=float)
            if peak_q.ndim != 1 or not len(peak_q):
                continue
            # Each peak has its own Q interval. Keep that interval instead of
            # resampling it onto the full fitted grid.
            add("I_peak", f"peak_{index}", f"peak {index}", x=peak_q, source=peak)
    elif descriptor.analysis == "carbon_fit":
        for key, role, label in (
            ("I_porod", "grain_porod", "grain Porod"),
            ("I_mp", "micropores", "micropores"),
            ("I_waxs", "diffraction", "diffraction"),
        ):
            add(key, role, label)
    elif descriptor.analysis == "modeling":
        for index, population in enumerate(result.get("populations") or (), 1):
            add("model_I", f"population_{index}", f"population {index}", source=population)
    return ResultBundle(
        descriptor=descriptor,
        records=tuple(records),
        styles=tuple(styles),
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
        "adapter": _reader_id(descriptor.analysis),
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
            ("number_distribution", "number_dist"),
            ("surface_distribution", "surface_dist"),
        ):
            if result.get(key) is not None:
                available.append(kind)
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
            x_log=descriptor.analysis != "waxs_peakfit",
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
    distributions = {
        "number_distribution": ("number_dist", "Number distribution", "number_density_per_radius"),
        "surface_distribution": ("surface_dist", "Surface distribution", "surface_density_per_radius"),
    }
    if kind in distributions and descriptor.analysis == "size_distribution":
        key, title, semantic = distributions[kind]
        radii = _array(result, "r_grid")
        curve = GenericCurve(
            x=radii,
            y=_array(result, key, length=len(radii)),
            label=f"{stem} — {descriptor.title} {title.lower()}",
            role=CurveRole.DISTRIBUTION,
            x_semantic="particle_radius",
            y_semantic=semantic,
            x_label="Radius",
            y_label=title,
            x_unit="angstrom",
            y_unit="1/angstrom",
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
