"""Pure Irena-compatible scattering plot transformations."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Protocol

import numpy as np

from bernardyn.core.models import Dataset, PlotSeries, SeriesView
from bernardyn.core.registry import Registry


@dataclass(frozen=True)
class ParameterSpec:
    id: str
    label: str
    default: float | None = None
    minimum: float | None = None
    required: bool = False


class PlotTransform(Protocol):
    id: str
    name: str
    version: str
    parameters: tuple[ParameterSpec, ...]
    default_x_label: str
    default_y_label: str
    default_x_log: bool
    default_y_log: bool

    def apply(self, dataset: Dataset, view: SeriesView) -> PlotSeries: ...


class TransformRegistry(Registry[PlotTransform]):
    def __init__(self) -> None:
        super().__init__("bernardyn.transforms")


@dataclass(frozen=True)
class FormulaTransform:
    id: str
    name: str
    x_formula: Callable[[np.ndarray, Mapping[str, float]], np.ndarray]
    y_formula: Callable[[np.ndarray, np.ndarray, Mapping[str, float]], np.ndarray]
    dx_formula: Callable[[np.ndarray, np.ndarray, Mapping[str, float]], np.ndarray]
    dy_formula: Callable[[np.ndarray, np.ndarray, np.ndarray, Mapping[str, float]], np.ndarray]
    valid_formula: Callable[[np.ndarray, np.ndarray, Mapping[str, float]], np.ndarray]
    default_x_label: str
    default_y_label: str
    x_unit_formula: Callable[[Dataset], str]
    y_unit_formula: Callable[[Dataset], str]
    parameters: tuple[ParameterSpec, ...] = ()
    version: str = "1.0"
    default_x_log: bool = False
    default_y_log: bool = False
    # Older versions whose snapshots are still exact for some views, mapped
    # to a predicate saying for which.  See ``snapshot_is_current``.
    equivalent_versions: Mapping[str, Callable[[SeriesView], bool]] = field(
        default_factory=dict
    )

    def apply(self, dataset: Dataset, view: SeriesView) -> PlotSeries:
        """Resolve one series.

        The series multiplier scales the measured intensity (and its
        uncertainty) *before* the view formula, as Irena does, so a
        multiplier shifts ln(I) in a Guinier view instead of changing its
        slope.  The offset is a display shift of the transformed Y.  For
        views linear in I (General I(Q), Kratky, Porod, ...) both orders
        give the same numbers.
        """
        params = {spec.id: spec.default for spec in self.parameters if spec.default is not None}
        params.update({key: float(value) for key, value in view.transform_parameters.items()})
        for spec in self.parameters:
            if spec.required and spec.id not in params:
                raise ValueError(f"{self.name} requires {spec.label}")
            if spec.id in params and spec.minimum is not None and params[spec.id] < spec.minimum:
                raise ValueError(f"{spec.label} must be at least {spec.minimum}")

        q = dataset.q
        multiplier = float(view.multiplier)
        with np.errstate(over="ignore", invalid="ignore"):
            intensity = dataset.intensity * multiplier
            uncertainty = (
                None if dataset.uncertainty is None else dataset.uncertainty * abs(multiplier)
            )
        in_range = np.ones(q.shape, dtype=bool)
        low, high = view.q_range
        if low is not None:
            in_range &= q >= low
        if high is not None:
            in_range &= q <= high
        with np.errstate(invalid="ignore"):
            valid = np.isfinite(q) & np.isfinite(intensity) & self.valid_formula(q, intensity, params)
        mask = in_range & valid
        source_indices = np.flatnonzero(mask)
        warnings: list[str] = []
        # Points the user trimmed with the Q range are a choice, not a data
        # problem; only points inside the range that the view cannot show
        # are reported.
        excluded = int(np.count_nonzero(in_range & ~valid))
        if excluded:
            warnings.append(
                f"{excluded} of {int(np.count_nonzero(in_range))} points were outside "
                "the valid plot domain"
            )

        q_valid = q[mask]
        i_valid = intensity[mask]
        with np.errstate(divide="ignore", invalid="ignore", over="ignore"):
            x = self.x_formula(q_valid, params)
            y = self.y_formula(q_valid, i_valid, params)
            dx = None
            if dataset.dq is not None:
                dx = self.dx_formula(q_valid, dataset.dq[mask], params)
            dy = None
            if uncertainty is not None:
                dy = self.dy_formula(q_valid, i_valid, uncertainty[mask], params)

        # Only the coordinates decide whether a measurement is drawable.  A
        # missing optional uncertainty stays NaN so the renderer omits that
        # one error bar instead of discarding the measurement itself.
        finite = np.isfinite(x) & np.isfinite(y)
        newly_invalid = int(len(finite) - np.count_nonzero(finite))
        if newly_invalid:
            warnings.append(f"{newly_invalid} transformed points were non-finite and were masked")
        x = x[finite]
        y = y[finite] + view.offset
        source_indices = source_indices[finite]
        if dx is not None:
            dx = np.abs(dx[finite])
            warnings.extend(_missing_uncertainty_warning("dX", dx))
        if dy is not None:
            dy = np.abs(dy[finite])
            warnings.extend(_missing_uncertainty_warning("dY", dy))

        return PlotSeries(
            series_id=view.id,
            dataset_id=dataset.id,
            x=x,
            y=y,
            dx=dx,
            dy=dy,
            source_indices=source_indices,
            label=view.legend_label or dataset.label,
            x_label=self.default_x_label,
            y_label=self.default_y_label,
            x_unit=self.x_unit_formula(dataset),
            y_unit=self.y_unit_formula(dataset),
            transform_id=self.id,
            transform_version=self.version,
            warnings=tuple(warnings),
        )


def _missing_uncertainty_warning(name: str, values: np.ndarray) -> list[str]:
    """Report points kept without an error bar because their uncertainty is unusable."""
    missing = int(len(values) - np.count_nonzero(np.isfinite(values)))
    if not missing:
        return []
    return [f"{missing} of {len(values)} points have no finite {name}; their error bars are omitted"]


def snapshot_is_current(transform: PlotTransform, version: str, view: SeriesView) -> bool:
    """Whether a snapshot written by ``version`` of a view is still exact.

    A snapshot of the current version always is.  An older version counts
    only where the transform declares it equivalent for this series (for
    example, a Guinier 1.0 snapshot with multiplier 1).  Plugin transforms
    without ``equivalent_versions`` compare versions only.
    """
    if version == transform.version:
        return True
    predicate = getattr(transform, "equivalent_versions", {}).get(version)
    return bool(predicate is not None and predicate(view))


def _unit_multiplier(view: SeriesView) -> bool:
    return float(view.multiplier) == 1.0


# Version 1.1 of the views that are not linear in I: the multiplier now
# scales I before the formula (it used to scale the transformed Y, which in
# a Guinier view changed the slope and so the apparent Rg).  Snapshots from
# 1.0 are identical whenever the multiplier is 1.
_MULTIPLIER_ON_INTENSITY = {"version": "1.1", "equivalent_versions": {"1.0": _unit_multiplier}}


def _all(q, intensity, params):
    return np.ones(q.shape, dtype=bool)


def _q_positive(q, intensity, params):
    return q > 0


def _i_positive(q, intensity, params):
    return intensity > 0


def _qi_positive(q, intensity, params):
    return (q > 0) & (intensity > 0)


def _q(q, params):
    return q


def _dq(q, dq, params):
    return dq


def _intensity(q, intensity, params):
    return intensity


def _dintensity(q, intensity, uncertainty, params):
    return uncertainty


def _q2(q, params):
    return q**2


def _dq2(q, dq, params):
    return 2 * np.abs(q) * dq


def _q4(q, params):
    return q**4


def _dq4(q, dq, params):
    return 4 * np.abs(q**3) * dq


def _unit_q(dataset):
    return dataset.q_unit


def _unit_i(dataset):
    return dataset.intensity_unit


def _unit_q2(dataset):
    return f"({dataset.q_unit})²"


def _unit_q4(dataset):
    return f"({dataset.q_unit})⁴"


def _unit_log(dataset):
    return "dimensionless"


def _unit_inverse_i(dataset):
    return f"1/({dataset.intensity_unit})"


def builtin_transforms(*, discover_plugins: bool = True) -> TransformRegistry:
    """Return a new registry populated with the standard Irena views."""
    registry = TransformRegistry()
    transforms = [
        FormulaTransform(
            "raw", "General I(Q)", _q, _intensity, _dq, _dintensity, _all,
            "q", "Intensity", _unit_q, _unit_i, default_x_log=True, default_y_log=True,
        ),
        FormulaTransform(
            "guinier", "Guinier", _q2, lambda q, i, p: np.log(i), _dq2,
            lambda q, i, di, p: di / i, _i_positive,
            "q²", "ln(Intensity)", _unit_q2, _unit_log,
            **_MULTIPLIER_ON_INTENSITY,
        ),
        FormulaTransform(
            "guinier_rod", "Guinier rod", _q2, lambda q, i, p: np.log(i * q), _dq2,
            lambda q, i, di, p: di / i, _qi_positive,
            "q²", "ln(Intensity·q)", _unit_q2, _unit_log,
            **_MULTIPLIER_ON_INTENSITY,
        ),
        FormulaTransform(
            "guinier_sheet", "Guinier sheet", _q2,
            lambda q, i, p: np.log(i * q**2), _dq2,
            lambda q, i, di, p: di / i, _qi_positive,
            "q²", "ln(Intensity·q²)", _unit_q2, _unit_log,
            **_MULTIPLIER_ON_INTENSITY,
        ),
        FormulaTransform(
            "kratky", "Kratky", _q, lambda q, i, p: i * q**2, _dq,
            lambda q, i, di, p: di * q**2, _all,
            "q", "Intensity·q²", _unit_q, lambda d: f"{d.intensity_unit}·({d.q_unit})²",
        ),
        # (qRg)² I(q)/I₀ versus qRg (Kieffer et al., J. Synchrotron Rad. 29,
        # 2022).  Version 1.0 left X as q; 2.0 normalises both axes so curves
        # with different Rg overlay.  Rg is treated as exact, so dX = Rg·dQ.
        FormulaTransform(
            "dimensionless_kratky", "Dimensionless Kratky",
            lambda q, p: q * p["Rg"],
            lambda q, i, p: i * (q * p["Rg"]) ** 2 / p["I0"],
            lambda q, dq, p: dq * p["Rg"],
            lambda q, i, di, p: di * (q * p["Rg"]) ** 2 / p["I0"], _q_positive,
            "qRg", "I(qRg)²/I₀", _unit_log, _unit_log,
            parameters=(
                ParameterSpec("I0", "I₀", minimum=np.finfo(float).tiny, required=True),
                ParameterSpec("Rg", "Rg", minimum=np.finfo(float).tiny, required=True),
            ),
            version="2.0",
        ),
        FormulaTransform(
            "porod", "Porod", _q4, lambda q, i, p: i * q**4, _dq4,
            lambda q, i, di, p: di * q**4, _all,
            "q⁴", "Intensity·q⁴", _unit_q4, lambda d: f"{d.intensity_unit}·({d.q_unit})⁴",
        ),
        FormulaTransform(
            "porod2", "Modified Porod 2", _q, lambda q, i, p: i * q**4, _dq,
            lambda q, i, di, p: di * q**4, _all,
            "q", "Intensity·q⁴", _unit_q, lambda d: f"{d.intensity_unit}·({d.q_unit})⁴",
        ),
        FormulaTransform(
            "porod3", "Modified Porod 3", _q, lambda q, i, p: i * q**3, _dq,
            lambda q, i, di, p: di * q**3, _all,
            "q", "Intensity·q³", _unit_q, lambda d: f"{d.intensity_unit}·({d.q_unit})³",
        ),
        FormulaTransform(
            "zimm", "Zimm", _q2, lambda q, i, p: 1 / i, _dq2,
            lambda q, i, di, p: di / i**2, _i_positive,
            "q²", "1/Intensity", _unit_q2, _unit_inverse_i,
            **_MULTIPLIER_ON_INTENSITY,
        ),
        FormulaTransform(
            "debye_bueche", "Debye–Bueche", _q2, lambda q, i, p: np.sqrt(1 / i), _dq2,
            lambda q, i, di, p: 0.5 * di * i ** (-1.5), _i_positive,
            "q²", "√(1/Intensity)", _unit_q2, lambda d: f"1/√({d.intensity_unit})",
            **_MULTIPLIER_ON_INTENSITY,
        ),
    ]
    for transform in transforms:
        registry.register(transform)
    if discover_plugins:
        registry.discover()
    return registry


def resolve_series(
    dataset: Dataset,
    view: SeriesView,
    registry: TransformRegistry,
    *,
    x_log: bool = False,
    y_log: bool = False,
) -> PlotSeries:
    """Transform and apply graph-axis validity without mutating source arrays."""
    result = registry.get(view.transform_id).apply(dataset, view)
    valid = np.ones(len(result.x), dtype=bool)
    if x_log:
        valid &= result.x > 0
    if y_log:
        valid &= result.y > 0
    if np.all(valid):
        return result
    removed = int(len(valid) - np.count_nonzero(valid))
    warnings = result.warnings + (f"{removed} points were invalid for logarithmic axes",)
    return PlotSeries(
        series_id=result.series_id,
        dataset_id=result.dataset_id,
        x=result.x[valid],
        y=result.y[valid],
        dx=None if result.dx is None else result.dx[valid],
        dy=None if result.dy is None else result.dy[valid],
        source_indices=result.source_indices[valid],
        label=result.label,
        x_label=result.x_label,
        y_label=result.y_label,
        x_unit=result.x_unit,
        y_unit=result.y_unit,
        transform_id=result.transform_id,
        transform_version=result.transform_version,
        warnings=warnings,
    )
