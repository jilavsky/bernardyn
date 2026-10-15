"""Read saved pyIrena fitting curves through its schema and result readers."""

from __future__ import annotations

import hashlib
from collections import OrderedDict
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

import h5py
import numpy as np

from bernardyn.core.models import CurveRole, GenericCurve, SeriesStyle
from bernardyn.core.units import parse_unit
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


# Recently read results, keyed by file identity.  Choosing curves and then
# loading several kinds from one file would otherwise re-read it each time.
_CACHE: OrderedDict[tuple[str, str, str, int, int], Any] = OrderedDict()
_CACHE_SIZE = 64


def _cached(kind: str, descriptor: ResultDescriptor, load: Callable[[ResultDescriptor], Any]) -> Any:
    """Return ``load(descriptor)``, reusing it while the file is unchanged."""
    stat = descriptor.path.stat()
    key = (kind, str(descriptor.path), descriptor.analysis, stat.st_size, stat.st_mtime_ns)
    if key in _CACHE:
        _CACHE.move_to_end(key)
        return _CACHE[key]
    value = load(descriptor)
    _CACHE[key] = value
    while len(_CACHE) > _CACHE_SIZE:
        _CACHE.popitem(last=False)
    return value


def clear_result_cache() -> None:
    _CACHE.clear()


def _result(descriptor: ResultDescriptor) -> Mapping[str, Any]:
    """Load one result with pyIrena's readers, including all Sizes curves."""
    return _cached("result", descriptor, _read_result)


def _read_result(descriptor: ResultDescriptor) -> Mapping[str, Any]:
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


def _stored_units(descriptor: ResultDescriptor) -> dict[str, str]:
    """Return the ``units`` attribute of each array directly in the result group."""
    return _cached("units", descriptor, _read_stored_units)


def _read_stored_units(descriptor: ResultDescriptor) -> dict[str, str]:
    from pyirena.io.schema import TOOL_REGISTRY

    units: dict[str, str] = {}
    with h5py.File(descriptor.path, "r") as handle:
        group = handle.get(TOOL_REGISTRY[descriptor.analysis]["group"])
        if not isinstance(group, h5py.Group):
            return units
        for name, item in group.items():
            if not isinstance(item, h5py.Dataset) or "units" not in item.attrs:
                continue
            value = item.attrs["units"]
            if isinstance(value, bytes):
                value = value.decode("utf-8", errors="replace")
            if str(value).strip():
                units[name] = str(value).strip()
    return units


def _registry_unit(analysis: str, key: str) -> str | None:
    from pyirena.io.schema import TOOL_REGISTRY

    for plot in TOOL_REGISTRY[analysis]["plots"]:
        if plot["y"] == key and plot.get("y_units"):
            return str(plot["y_units"])
    return None


def _is_arbitrary(unit: str | None) -> bool:
    return unit is None or parse_unit(unit) == parse_unit("arb")


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
    fingerprint, result_metadata, provenance = _result_context(descriptor, result)
    stem = descriptor.path.stem
    records: list[ScatteringRecord] = []
    styles: list[SeriesStyle] = []
    stored = _stored_units(descriptor)
    q_key = "model_q" if descriptor.analysis == "modeling" else "Q"
    q_unit = stored.get(q_key, "1/angstrom")
    # Modeling saves no copy of the data it fitted; use the file's primary
    # scattering curve, which is what pyIrena Modeling reads by default.
    primary = (
        _primary_measured(descriptor)
        if descriptor.analysis == "modeling" and result.get("intensity_data") is None
        else None
    )
    has_measured = result.get("intensity_data") is not None or primary is not None
    measured_unit = (
        stored.get("intensity_data")
        or _registry_unit(descriptor.analysis, "intensity_data")
        or "1/cm"
    )
    model_key = {
        "modeling": "model_I",
        "simple_fits": "I_model",
        "waxs_peakfit": "I_fit",
        "carbon_fit": "I_model",
    }.get(descriptor.analysis, "intensity_model")

    if primary is not None:
        records.append(replace(
            primary,
            label=f"{stem} — {descriptor.title} data",
            metadata={**primary.metadata, "bernardyn_result": {
                **result_metadata,
                "role": "measured",
                "measured_source": "primary_scattering_data",
                "intensity_unit_source": "file",
            }},
            provenance={**primary.provenance, "result": result_metadata},
        ))
        styles.append(SeriesStyle(
            line_style="none", symbol="o", show_error_bars=primary.uncertainty is not None,
        ))

    def intensity_unit(file_key: str, role: str) -> tuple[str, str]:
        """Choose a curve's intensity unit and record where it came from.

        A fitted model, background, or component shares the measured data's
        units: it was fitted to them.  Some producers label such arrays
        ``arb`` (pyIrena Simple Fits ``I_model``), which would otherwise put
        data and fit on one axis in different units.
        """
        if role == "measured":
            return measured_unit, "file" if "intensity_data" in stored else "default"
        own = stored.get(file_key)
        if primary is not None and _is_arbitrary(own):
            return primary.intensity_unit, "measured_data"
        if has_measured and _is_arbitrary(own):
            return measured_unit, "measured_data"
        if own is not None:
            return own, "file"
        registry = _registry_unit(descriptor.analysis, file_key)
        return (registry, "registry") if registry else ("1/cm", "default")

    def add(
        key: str, role: str, label: str, *, x: np.ndarray = q,
        source: Mapping[str, Any] | None = None,
    ) -> None:
        values = result if source is None else source
        if values.get(key) is None:
            return
        y = _array(values, key, length=len(x))
        # The reader renames each tool's total-model array to
        # ``intensity_model``.  Peak and population arrays live in subgroups
        # without top-level units; they are components of that total fit.
        file_key = model_key if source is not None or key == "intensity_model" else key
        unit, unit_source = intensity_unit(file_key, role)
        records.append(ScatteringRecord(
            q=x,
            intensity=y,
            uncertainty=uncertainty if role == "measured" else None,
            # pyIrena stores the measured data's own uncertainty with a fit.
            uncertainty_kind="measured" if role == "measured" else None,
            q_unit=q_unit,
            intensity_unit=unit,
            label=f"{stem} — {descriptor.title} {label}",
            metadata={"bernardyn_result": {
                **result_metadata, "role": role, "intensity_unit_source": unit_source,
            }},
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


def _primary_measured(descriptor: ResultDescriptor) -> ScatteringRecord | None:
    """Return the file's preferred primary I(Q) curve, or None if it has none."""
    from bernardyn.io.sources import builtin_sources

    sources = builtin_sources(discover_plugins=False)
    try:
        chosen = sources.select_preferred_locations(sources.discover_path(descriptor.path))
        if len(chosen) != 1:
            return None
        return sources.load_location(chosen[0])
    except (OSError, KeyError, ValueError, RuntimeError):
        return None


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
    if descriptor.analysis == "modeling" and _modeling_populations(result):
        available.append("volume_distribution")
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


def _modeling_populations(result: Mapping[str, Any]) -> list[tuple[int, Mapping[str, Any]]]:
    """Return (1-based index, population) pairs that store a volume distribution."""
    return [
        (index, population)
        for index, population in enumerate(result.get("populations") or (), 1)
        if population.get("radius_grid") is not None and population.get("volume_dist") is not None
    ]


def load_result_curves(descriptor: ResultDescriptor, kind: str) -> tuple[ResultCurveBundle, ...]:
    """Load every curve of one kind; Modeling has one distribution per population."""
    if descriptor.analysis == "modeling" and kind == "volume_distribution":
        result = _result(descriptor)
        return tuple(
            load_result_curve(descriptor, f"population_{index}_volume_distribution")
            for index, _ in _modeling_populations(result)
        )
    return (load_result_curve(descriptor, kind),)


def _modeling_volume_distribution(
    descriptor: ResultDescriptor, result: Mapping[str, Any], kind: str
) -> ResultCurveBundle:
    fingerprint, result_metadata, provenance = _result_context(descriptor, result)
    populations = dict(_modeling_populations(result))
    try:
        index = int(kind.split("_")[1])
        population = populations[index]
    except (IndexError, KeyError, ValueError):
        raise ValueError(f"{kind!r} is not available for {descriptor.title}") from None
    radii = _array(population, "radius_grid")
    curve = GenericCurve(
        x=radii,
        y=_array(population, "volume_dist", length=len(radii)),
        label=f"{descriptor.path.stem} — {descriptor.title} population {index} volume distribution",
        role=CurveRole.DISTRIBUTION,
        x_semantic="particle_radius",
        y_semantic="volume_fraction_density_per_radius",
        x_label="Radius",
        y_label="Volume fraction density",
        # pyIrena stores no units here.  Modeling normalises each population
        # so that the integral over radius equals its volume fraction
        # (pyirena.core.modeling.build_distributions), as for Size Distribution.
        x_unit="angstrom",
        y_unit="volume_fraction/angstrom",
        metadata={"bernardyn_result": {
            **result_metadata,
            "role": kind,
            "population": index,
            "unit_source": "pyirena_modeling_normalisation",
        }},
        provenance=provenance,
        source_fingerprint=fingerprint,
    )
    return ResultCurveBundle(
        descriptor=descriptor,
        curve=curve,
        style=SeriesStyle(line_style="solid", symbol=None),
        graph_title=f"{descriptor.title} volume distribution",
        x_log=False,
        y_log=False,
    )


def load_result_curve(descriptor: ResultDescriptor, kind: str) -> ResultCurveBundle:
    """Load a supported non-I(Q) curve without assigning scattering semantics."""
    result = _result(descriptor)
    if not result.get("found"):
        raise ValueError(f"{descriptor.title} is no longer available in {descriptor.path.name}")
    if descriptor.analysis == "modeling" and kind.startswith("population_"):
        return _modeling_volume_distribution(descriptor, result, kind)
    fingerprint, result_metadata, provenance = _result_context(descriptor, result)
    stem = descriptor.path.stem
    stored = _stored_units(descriptor)
    radius_unit = stored.get("r_grid", "angstrom")
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
            x_unit=stored.get("Q", "1/angstrom"),
            y_unit=stored.get("residuals", "dimensionless"),
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
            x_unit=radius_unit,
            y_unit=stored.get("distribution", "volume_fraction/angstrom"),
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
            x_unit=radius_unit,
            y_unit=stored.get(key, "1/angstrom"),
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
            x_unit=radius_unit,
            y_unit=stored.get(key, y_unit),
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
