"""Read-only scattering-data discovery and loading.

The adapters prefer PyIrena's mature readers when the compatible public or
legacy API is installed, and retain a small standard-HDF5/text fallback so
portable Bernardyn packages are not coupled to GUI-private PyIrena code.
"""

from __future__ import annotations

import hashlib
import logging
import warnings
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Protocol
from uuid import NAMESPACE_URL, uuid5

import h5py
import numpy as np

from bernardyn.core.models import Dataset, json_value
from bernardyn.core.registry import Registry

log = logging.getLogger(__name__)

Q_UNIT_SCALE = {
    "1/A": 1.0,
    "1/angstrom": 1.0,
    "1/Å": 1.0,
    "1/nm": 0.1,
    "1/pm": 100.0,
    "1/um": 1e-4,
    "1/mm": 1e-7,
    "a^-1": 1.0,
    "angstrom^-1": 1.0,
    "å^-1": 1.0,
    "nm^-1": 0.1,
    "pm^-1": 100.0,
    "um^-1": 1e-4,
    "µm^-1": 1e-4,
    "mm^-1": 1e-7,
}


def _location_id(path: Path, internal_path: str | None) -> str:
    return str(uuid5(NAMESPACE_URL, f"{path.resolve()}::{internal_path or ''}"))


def _fingerprint(path: Path) -> str:
    stat = path.stat()
    value = f"{path.resolve()}:{stat.st_size}:{stat.st_mtime_ns}".encode()
    return hashlib.sha256(value).hexdigest()


def _decode(value: Any) -> Any:
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    if isinstance(value, np.ndarray):
        return [_decode(item) for item in value.tolist()]
    if isinstance(value, np.generic):
        return _decode(value.item())
    return json_value(value)


def _attrs(obj: h5py.Group | h5py.Dataset) -> dict[str, Any]:
    return {str(key): _decode(value) for key, value in obj.attrs.items()}


def _q_unit_metadata(path: Path, internal_path: str | None) -> dict[str, Any]:
    """Report a simple Q-unit hint while browsing, without reading arrays."""
    if not internal_path:
        return {}
    try:
        with h5py.File(path, "r") as handle:
            group = handle[internal_path]
            if not isinstance(group, h5py.Group):
                return {}
            names = {key.lower(): key for key in group.keys()}
            q_name = next((names[key] for key in ("q", "qvec", "q_vector") if key in names), None)
            if q_name is None or not isinstance(group[q_name], h5py.Dataset):
                return {}
            unit = _decode(group[q_name].attrs.get("units"))
            return {"q_unit_missing": not bool(str(unit or "").strip()), "q_unit": unit}
    except (OSError, KeyError):
        return {}


def _pyirena_fit_metadata(path: Path, variant: str) -> dict[str, Any]:
    if variant == "slit-smeared":
        return {}
    try:
        from pyirena.io.nxcansas_simple_fits import load_simple_fit_results

        result = load_simple_fit_results(path)
    except (ImportError, KeyError, OSError, ValueError):
        return {}
    if not result or not result.get("found", True):
        return {}
    params = result.get("params", {}) or {}
    derived = result.get("derived", {}) or {}
    values: dict[str, float] = {}
    for key in ("I0", "Rg"):
        value = params.get(key, derived.get(key))
        try:
            values[key] = float(value)
        except (TypeError, ValueError):
            pass
    if not values:
        return {}
    return {
        **values,
        "pyirena_simple_fit": {
            "model": result.get("model"),
            "params": values,
            "timestamp": result.get("timestamp"),
        },
    }


@dataclass(frozen=True)
class ScatteringLocation:
    path: Path
    adapter_id: str
    internal_path: str | None = None
    display_name: str = ""
    variant: str = "default"
    metadata: Mapping[str, Any] = field(default_factory=dict)
    id: str = ""

    def __post_init__(self) -> None:
        path = Path(self.path).expanduser().resolve()
        object.__setattr__(self, "path", path)
        object.__setattr__(self, "id", self.id or _location_id(path, self.internal_path))
        object.__setattr__(self, "display_name", self.display_name or path.name)
        object.__setattr__(self, "metadata", dict(self.metadata))


@dataclass(frozen=True)
class ScatteringRecord:
    q: np.ndarray
    intensity: np.ndarray
    uncertainty: np.ndarray | None = None
    dq: np.ndarray | None = None
    q_unit: str = "1/angstrom"
    intensity_unit: str = "1/cm"
    label: str = "Dataset"
    metadata: Mapping[str, Any] = field(default_factory=dict)
    provenance: Mapping[str, Any] = field(default_factory=dict)
    source_fingerprint: str | None = None

    def to_dataset(self) -> Dataset:
        original_unit = str(self.q_unit).strip()
        scale = Q_UNIT_SCALE.get(original_unit, Q_UNIT_SCALE.get(original_unit.lower()))
        assumed = scale is None
        scale = 1.0 if scale is None else scale
        metadata = dict(self.metadata)
        metadata["q_unit_conversion"] = {
            "original_unit": original_unit,
            "canonical_unit": "1/angstrom",
            "scale": scale,
            "assumed_inverse_angstrom": assumed,
        }
        return Dataset(
            q=np.asarray(self.q, dtype=float) * scale,
            intensity=self.intensity,
            uncertainty=self.uncertainty,
            dq=None if self.dq is None else np.asarray(self.dq, dtype=float) * scale,
            label=self.label,
            q_unit="1/angstrom",
            intensity_unit=self.intensity_unit,
            metadata=metadata,
            provenance=self.provenance,
            source_fingerprint=self.source_fingerprint,
        )


class SourceAdapter(Protocol):
    id: str
    suffixes: tuple[str, ...]

    def discover(self, path: Path) -> list[ScatteringLocation]: ...

    def load(
        self,
        location: ScatteringLocation,
        *,
        q_unit: str = "1/A",
        error_fraction: float = 0.05,
    ) -> ScatteringRecord: ...


class SourceRegistry(Registry[SourceAdapter]):
    def __init__(self) -> None:
        super().__init__("bernardyn.sources")

    def adapter_for(self, path: Path) -> SourceAdapter:
        suffix = Path(path).suffix.lower()
        for adapter in self:
            if suffix in adapter.suffixes:
                return adapter
        raise ValueError(f"no source adapter supports {path}")

    def discover_path(self, path: str | Path) -> list[ScatteringLocation]:
        resolved = Path(path).expanduser().resolve()
        return self.adapter_for(resolved).discover(resolved)

    def preferred_locations(self, path: str | Path) -> list[ScatteringLocation]:
        """Return the normal plotting choice for one source file.

        PyIrena orders NXcanSAS discovery with the NeXus ``@default`` SASdata
        first and suppresses slit-smeared siblings for its normal data path.
        Bernardyn follows that convention for file-list loading: one main
        curve per file, no picker dialog.  Explicit dataset browsing remains
        available for the occasional non-default curve.
        """
        return self.select_preferred_locations(self.discover_path(path))

    @staticmethod
    def select_preferred_locations(
        locations: list[ScatteringLocation],
    ) -> list[ScatteringLocation]:
        """Select the normal primary curve from already-discovered locations."""
        if not locations:
            return []
        non_smeared = [location for location in locations if location.variant != "slit-smeared"]
        return [non_smeared[0] if non_smeared else locations[0]]

    def load_location(self, location: ScatteringLocation, **options: Any) -> ScatteringRecord:
        return self.get(location.adapter_id).load(location, **options)


class HDF5SourceAdapter:
    id = "hdf5"
    suffixes = (".h5", ".hdf5", ".hdf", ".nxs")

    def discover(self, path: Path) -> list[ScatteringLocation]:
        if not path.is_file():
            raise FileNotFoundError(path)
        pyirena_locations = self._discover_with_pyirena(path)
        if pyirena_locations:
            return pyirena_locations
        locations: list[ScatteringLocation] = []
        with h5py.File(path, "r") as handle:
            def visitor(name: str, obj: h5py.Group | h5py.Dataset) -> None:
                if not isinstance(obj, h5py.Group):
                    return
                names = {key.lower(): key for key in obj.keys()}
                q_name = next((names[key] for key in ("q", "qvec", "q_vector") if key in names), None)
                i_name = next(
                    (names[key] for key in ("i", "intensity", "r", "data") if key in names), None
                )
                if q_name is None or i_name is None:
                    return
                if not isinstance(obj[q_name], h5py.Dataset) or not isinstance(obj[i_name], h5py.Dataset):
                    return
                group_path = f"/{name}" if name else "/"
                locations.append(
                    ScatteringLocation(
                        path=path,
                        adapter_id=self.id,
                        internal_path=group_path,
                        display_name=f"{path.name}: {group_path}",
                        variant="slit-smeared" if "smr" in name.lower() else "default",
                        metadata={
                            "mapping": {"q": q_name, "intensity": i_name},
                            **_q_unit_metadata(path, group_path),
                        },
                    )
                )

            handle.visititems(visitor)
        if not locations:
            raise ValueError(f"no recognizable 1D scattering datasets found in {path.name}")
        return self._prefer_sasdata_locations(locations)

    @staticmethod
    def _prefer_sasdata_locations(
        locations: list[ScatteringLocation],
    ) -> list[ScatteringLocation]:
        """Use NXcanSAS SASdata curves when a file also exposes auxiliaries.

        Instrument files commonly contain Blank/QRS/background curves beside
        the actual NXcanSAS ``sasdata`` entry.  Those auxiliaries are not the
        normal plotting target.  If a file has SASdata groups, keep all of
        them (including an explicitly available slit-smeared sibling); for a
        simple HDF5 file without SASdata, retain every discoverable 1-D group.
        """
        sasdata = [
            location
            for location in locations
            if location.internal_path and location.internal_path.rstrip("/").lower().endswith("/sasdata")
        ]
        return sasdata or locations

    def _discover_with_pyirena(self, path: Path) -> list[ScatteringLocation]:
        try:
            from pyirena.io import discover_scattering

            discovered_locations = discover_scattering(path)
            locations = [
                ScatteringLocation(
                    path=item.path,
                    adapter_id=self.id,
                    internal_path=item.internal_path,
                    display_name=item.display_name,
                    variant=item.variant,
                    metadata={
                        **dict(item.metadata),
                        "discovery_index": index,
                        **_q_unit_metadata(path, item.internal_path),
                    },
                )
                for index, item in enumerate(discovered_locations)
            ]
            return self._prefer_sasdata_locations(locations)
        except (ImportError, ValueError):
            pass
        try:
            from pyirena.io.hdf5 import list_nxcansas_datasets

            discovered = list_nxcansas_datasets(str(path.parent), path.name, include_smr=True)
        except (ImportError, TypeError):
            try:
                from pyirena.io.hdf5 import list_nxcansas_datasets

                discovered = list_nxcansas_datasets(str(path.parent), path.name)
            except Exception:
                return []
        except Exception:
            return []
        locations = [
            ScatteringLocation(
                path=path,
                adapter_id=self.id,
                internal_path=str(item["path"]),
                display_name=f"{path.name}: {item.get('name', item['path'])}",
                variant="slit-smeared" if "smr" in str(item["path"]).lower() else "default",
                metadata={
                    "entry": item.get("entry"),
                    "name": item.get("name"),
                    **_q_unit_metadata(path, str(item["path"])),
                },
            )
            for item in discovered
        ]
        return self._prefer_sasdata_locations(locations)

    def load(
        self,
        location: ScatteringLocation,
        *,
        q_unit: str = "1/A",
        error_fraction: float = 0.05,
    ) -> ScatteringRecord:
        try:
            from pyirena.io import ScatteringLocation as PyIrenaLocation
            from pyirena.io import load_scattering

            record = load_scattering(
                PyIrenaLocation(
                    location.path,
                    internal_path=location.internal_path,
                    display_name=location.display_name,
                    variant=location.variant,
                    metadata=location.metadata,
                ),
                q_unit=q_unit,
                error_fraction=error_fraction,
            )
            metadata = dict(record.metadata)
            metadata.update(_pyirena_fit_metadata(location.path, location.variant))
            if location.metadata.get("q_unit_missing"):
                metadata["q_unit_assumed"] = q_unit
                provenance = {**dict(record.provenance), "q_unit_assumed": q_unit}
                record_q_unit = q_unit
            else:
                provenance = record.provenance
                record_q_unit = record.q_unit
            return ScatteringRecord(
                q=record.q,
                intensity=record.intensity,
                uncertainty=record.uncertainty,
                dq=record.dq,
                q_unit=record_q_unit,
                intensity_unit=record.intensity_unit,
                label=record.label,
                metadata=metadata,
                provenance=provenance,
                source_fingerprint=record.source_fingerprint,
            )
        except (ImportError, ValueError):
            pass
        try:
            from pyirena.io.hdf5 import readGenericNXcanSAS

            result = readGenericNXcanSAS(
                str(location.path.parent),
                location.path.name,
                data_path=location.internal_path,
            )
        except ImportError:
            result = None
        if result is not None:
            return self._record_from_mapping(location, result, q_unit=q_unit)
        return self._load_direct(location, q_unit=q_unit)

    def _record_from_mapping(
        self, location: ScatteringLocation, result: Mapping[str, Any], *, q_unit: str
    ) -> ScatteringRecord:
        q = result.get("Q")
        intensity = result.get("Intensity", result.get("I"))
        if q is None or intensity is None:
            raise ValueError(f"{location.display_name} does not contain Q and intensity")
        q_attrs = result.get(
            "QAttrs", result.get("Q_attrs", result.get("Q_attributes", {}))
        ) or {}
        i_attrs = result.get(
            "IntensityAttrs",
            result.get("I_attrs", result.get("Int_attributes", {})),
        ) or {}
        metadata = {
            key: _decode(value)
            for key, value in result.items()
            if key.lower().endswith(("attrs", "attributes"))
        }
        metadata.update(_pyirena_fit_metadata(location.path, location.variant))
        source_q_unit = str(_decode(q_attrs.get("units")) or "").strip()
        missing_q_unit = not bool(source_q_unit)
        if missing_q_unit:
            metadata["q_unit_assumed"] = q_unit
        return ScatteringRecord(
            q=np.asarray(q, dtype=float),
            intensity=np.asarray(intensity, dtype=float),
            uncertainty=None if result.get("Error") is None else np.asarray(result["Error"], dtype=float),
            dq=None if result.get("dQ") is None else np.asarray(result["dQ"], dtype=float),
            q_unit=source_q_unit or q_unit,
            intensity_unit=str(_decode(i_attrs.get("units", "1/cm"))),
            label=location.display_name,
            metadata=metadata,
            provenance={
                "source_name": location.path.name,
                "source_path": str(location.path),
                "internal_path": location.internal_path,
                "adapter": "pyirena.io.hdf5",
                "variant": location.variant,
                **({"q_unit_assumed": q_unit} if missing_q_unit else {}),
            },
            source_fingerprint=_fingerprint(location.path),
        )

    def _load_direct(self, location: ScatteringLocation, *, q_unit: str) -> ScatteringRecord:
        with h5py.File(location.path, "r") as handle:
            if not location.internal_path or location.internal_path not in handle:
                raise ValueError(f"HDF5 group not found: {location.internal_path}")
            group = handle[location.internal_path]
            if not isinstance(group, h5py.Group):
                raise ValueError("selected HDF5 location is not a group")
            names = {key.lower(): key for key in group.keys()}
            mapping = dict(location.metadata.get("mapping", {}))
            q_name = mapping.get("q") or next(
                (names[key] for key in ("q", "qvec", "q_vector") if key in names), None
            )
            i_name = mapping.get("intensity") or next(
                (names[key] for key in ("i", "intensity", "r", "data") if key in names), None
            )
            e_name = mapping.get("uncertainty") or next(
                (names[key] for key in ("idev", "error", "i_error", "s") if key in names), None
            )
            dq_name = mapping.get("dq") or next(
                (names[key] for key in ("qdev", "dq", "q_error") if key in names), None
            )
            if q_name is None or i_name is None:
                raise ValueError("selected group has no Q/intensity mapping")
            q_dataset = group[q_name]
            i_dataset = group[i_name]
            q = np.asarray(q_dataset[()], dtype=float)
            intensity = np.asarray(i_dataset[()], dtype=float)
            uncertainty = None if e_name is None else np.asarray(group[e_name][()], dtype=float)
            dq = None if dq_name is None else np.asarray(group[dq_name][()], dtype=float)
            source_q_unit = str(_decode(q_dataset.attrs.get("units")) or "").strip()
            missing_q_unit = not bool(source_q_unit)
            return ScatteringRecord(
                q=q,
                intensity=intensity,
                uncertainty=uncertainty,
                dq=dq,
                q_unit=source_q_unit or q_unit,
                intensity_unit=str(_decode(i_dataset.attrs.get("units", "1/cm"))),
                label=location.display_name,
                metadata={
                    "group_attributes": _attrs(group),
                    **({"q_unit_assumed": q_unit} if missing_q_unit else {}),
                    **_pyirena_fit_metadata(location.path, location.variant),
                },
                provenance={
                    "source_name": location.path.name,
                    "source_path": str(location.path),
                    "internal_path": location.internal_path,
                    "adapter": self.id,
                    "variant": location.variant,
                    **({"q_unit_assumed": q_unit} if missing_q_unit else {}),
                },
                source_fingerprint=_fingerprint(location.path),
            )


class TextSourceAdapter:
    id = "text"
    suffixes = (".dat", ".txt", ".csv")

    def discover(self, path: Path) -> list[ScatteringLocation]:
        if not path.is_file():
            raise FileNotFoundError(path)
        return [ScatteringLocation(path=path, adapter_id=self.id, display_name=path.name)]

    def load(
        self,
        location: ScatteringLocation,
        *,
        q_unit: str = "1/A",
        error_fraction: float = 0.05,
    ) -> ScatteringRecord:
        if q_unit not in Q_UNIT_SCALE:
            raise ValueError(f"unsupported Q unit {q_unit!r}")
        if error_fraction <= 0:
            raise ValueError("error_fraction must be positive")
        try:
            from pyirena.io import ScatteringLocation as PyIrenaLocation
            from pyirena.io import load_scattering

            with warnings.catch_warnings():
                warnings.simplefilter("ignore", UserWarning)
                record = load_scattering(
                    PyIrenaLocation(
                        location.path,
                        display_name=location.display_name,
                        variant="text",
                    ),
                    q_unit=q_unit,
                    error_fraction=error_fraction,
                )
            return ScatteringRecord(
                q=record.q,
                intensity=record.intensity,
                uncertainty=record.uncertainty,
                dq=record.dq,
                q_unit=record.q_unit,
                intensity_unit=record.intensity_unit,
                label=record.label,
                metadata=record.metadata,
                provenance=record.provenance,
                source_fingerprint=record.source_fingerprint,
            )
        except (ImportError, ValueError):
            pass
        text = self._read_text(location.path)
        delimiter = self._delimiter(text)
        rows: list[list[float]] = []
        skipped = 0
        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line or line.startswith(("#", ";", "//")):
                continue
            fields = line.split(delimiter) if delimiter is not None else line.split()
            try:
                values = [float(field.strip().replace("D", "E").replace("d", "e")) for field in fields]
            except ValueError:
                skipped += 1
                continue
            if len(values) < 2:
                skipped += 1
                continue
            rows.append(values[:4])
        if not rows:
            raise ValueError(f"no numeric Q/intensity rows found in {location.path.name}")
        q = np.asarray([row[0] for row in rows], dtype=float) * Q_UNIT_SCALE[q_unit]
        intensity = np.asarray([row[1] for row in rows], dtype=float)
        uncertainty = np.asarray(
            [row[2] if len(row) >= 3 else np.nan for row in rows], dtype=float
        )
        bad_error = ~np.isfinite(uncertainty) | (uncertainty <= 0)
        uncertainty[bad_error] = np.abs(intensity[bad_error]) * error_fraction
        dq = None
        if any(len(row) >= 4 for row in rows):
            dq = np.asarray([row[3] if len(row) >= 4 else np.nan for row in rows], dtype=float)
            dq *= Q_UNIT_SCALE[q_unit]
        return ScatteringRecord(
            q=q,
            intensity=intensity,
            uncertainty=uncertainty,
            dq=dq,
            q_unit="1/angstrom",
            intensity_unit="1/cm",
            label=location.path.stem,
            metadata={
                "rows_loaded": len(rows),
                "rows_skipped": skipped,
                "uncertainties_synthesized": int(np.count_nonzero(bad_error)),
                "error_fraction": error_fraction,
            },
            provenance={
                "source_name": location.path.name,
                "source_path": str(location.path),
                "adapter": self.id,
                "q_unit_assumed": q_unit,
            },
            source_fingerprint=_fingerprint(location.path),
        )

    @staticmethod
    def _read_text(path: Path) -> str:
        try:
            return path.read_text(encoding="utf-8-sig")
        except UnicodeDecodeError:
            return path.read_text(encoding="latin-1")

    @staticmethod
    def _delimiter(text: str) -> str | None:
        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line or line.startswith(("#", ";", "//")):
                continue
            if "," in line:
                return ","
            if "\t" in line:
                return "\t"
        return None


def builtin_sources(*, discover_plugins: bool = True) -> SourceRegistry:
    registry = SourceRegistry()
    registry.register(HDF5SourceAdapter())
    registry.register(TextSourceAdapter())
    if discover_plugins:
        registry.discover()
    return registry
