"""Plan and load one saved-result import across many files.

The GUI asks once for an analysis and the curve kinds wanted, rather than
twice per file.  This module, which needs no Qt, works out which files offer
what, loads the selection, and groups the curves so that each kind becomes
one comparison graph instead of one graph per file.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from bernardyn.io.results import (
    ResultBundle,
    ResultCurveBundle,
    ResultDescriptor,
    available_curve_kinds,
    discover_results,
    load_result_bundle,
    load_result_curves,
)

IQ_KIND = "iq"
KIND_LABELS = {
    IQ_KIND: "Data + fit I(Q)",
    "residuals": "Residuals",
    "volume_distribution": "Volume distribution",
    "number_distribution": "Number distribution",
    "surface_distribution": "Surface distribution",
    "cumulative_volume_distribution": "Cumulative volume distribution",
    "cumulative_number_distribution": "Cumulative number distribution",
    "cumulative_surface_distribution": "Cumulative surface distribution",
}


def kind_label(kind: str) -> str:
    return KIND_LABELS.get(kind, kind.replace("_", " ").capitalize())


@dataclass(frozen=True)
class FileResults:
    """Saved results found in one file, with the curve kinds each offers."""

    path: Path
    kinds: dict[str, tuple[str, ...]] = field(default_factory=dict)
    descriptors: dict[str, ResultDescriptor] = field(default_factory=dict)
    error: str | None = None


@dataclass(frozen=True)
class ResultSurvey:
    """What every selected file offers, in selection order."""

    files: tuple[FileResults, ...]

    def analyses(self) -> list[tuple[str, str, int]]:
        """Return (analysis, title, number of files) in first-seen order."""
        found: dict[str, tuple[str, int]] = {}
        for item in self.files:
            for analysis, descriptor in item.descriptors.items():
                title, count = found.get(analysis, (descriptor.title, 0))
                found[analysis] = (title, count + 1)
        return [(analysis, title, count) for analysis, (title, count) in found.items()]

    def kinds(self, analysis: str) -> list[tuple[str, int]]:
        """Return (kind, number of files offering it) for one analysis."""
        counts: dict[str, int] = {}
        for item in self.files:
            for kind in item.kinds.get(analysis, ()):
                counts[kind] = counts.get(kind, 0) + 1
        return list(counts.items())

    def skipped(self, analysis: str, kinds: tuple[str, ...]) -> list[tuple[Path, str]]:
        """Files that contribute nothing to this selection, with the reason."""
        result: list[tuple[Path, str]] = []
        for item in self.files:
            if item.error is not None:
                result.append((item.path, item.error))
            elif analysis not in item.kinds:
                result.append((item.path, "no saved result of this analysis"))
            elif not set(kinds) & set(item.kinds[analysis]):
                result.append((item.path, "none of the chosen curves are stored"))
        return result


def survey_results(paths: list[str | Path]) -> ResultSurvey:
    """Inspect each file once.  A failure is recorded, never raised."""
    files: list[FileResults] = []
    for value in paths:
        path = Path(value).expanduser().resolve()
        try:
            descriptors = discover_results(path)
            files.append(FileResults(
                path=path,
                kinds={
                    item.analysis: (IQ_KIND, *available_curve_kinds(item)) for item in descriptors
                },
                descriptors={item.analysis: item for item in descriptors},
            ))
        except Exception as exc:
            files.append(FileResults(path=path, error=str(exc) or type(exc).__name__))
    return ResultSurvey(tuple(files))


@dataclass(frozen=True)
class ResultBatch:
    """Loaded curves for one selection, grouped for graph creation.

    ``iq`` holds one bundle per file, in selection order.  ``curves`` maps each
    other kind to its curves across files, each tagged with its file's index
    in the selection so that one file keeps one colour on every graph.
    """

    analysis: str
    iq: tuple[tuple[int, ResultBundle], ...]
    curves: dict[str, tuple[tuple[int, ResultCurveBundle], ...]]
    skipped: tuple[tuple[Path, str], ...]


def load_result_batch(survey: ResultSurvey, analysis: str, kinds: tuple[str, ...]) -> ResultBatch:
    """Load the chosen kinds from every file that offers them.

    A file that fails to load is skipped and reported; it does not abort the
    other files.
    """
    skipped = list(survey.skipped(analysis, kinds))
    iq: list[tuple[int, ResultBundle]] = []
    curves: dict[str, list[tuple[int, ResultCurveBundle]]] = {kind: [] for kind in kinds if kind != IQ_KIND}
    contributing = [
        item for item in survey.files
        if item.error is None and set(kinds) & set(item.kinds.get(analysis, ()))
    ]
    for index, item in enumerate(contributing):
        descriptor = item.descriptors[analysis]
        try:
            loaded_iq = (
                load_result_bundle(descriptor) if IQ_KIND in kinds and IQ_KIND in item.kinds[analysis] else None
            )
            loaded = {
                kind: load_result_curves(descriptor, kind)
                for kind in curves
                if kind in item.kinds[analysis]
            }
        except Exception as exc:
            skipped.append((item.path, str(exc) or type(exc).__name__))
            continue
        if loaded_iq is not None:
            iq.append((index, loaded_iq))
        for kind, bundles in loaded.items():
            curves[kind].extend((index, bundle) for bundle in bundles)
    return ResultBatch(
        analysis=analysis,
        iq=tuple(iq),
        curves={kind: tuple(items) for kind, items in curves.items() if items},
        skipped=tuple(skipped),
    )
