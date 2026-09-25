"""Shared dataset-category choices for the browser and graph inspector."""

from __future__ import annotations

from typing import Mapping

from bernardyn.core.models import Dataset, GenericCurve

# The stable ids, rather than visible labels, are kept in Qt item data.  This
# makes a saved result's scientific role available in both places that list
# graph data without making either widget own result-import knowledge.
DATASET_FILTERS = (
    ("All data", "all"),
    ("SAS data", "sas"),
    ("Unified Fit results", "unified_fit_measured"),
    # Filter ids match the persisted ``bernardyn_result.role`` values. The
    # user-facing term remains "model", while Unified Fit stores it as "fit".
    ("Unified Fit model", "unified_fit_fit"),
    ("Unified Fit residuals", "unified_fit_residuals"),
    ("Size Distribution results", "size_distribution_measured"),
    ("Size Distribution model", "size_distribution_fit"),
    ("Size Distribution residuals", "size_distribution_residuals"),
    ("Size Distribution volume distribution", "size_distribution_volume_distribution"),
    ("Size Distribution cumulative volume", "size_distribution_cumulative_volume_distribution"),
    ("Size Distribution cumulative number", "size_distribution_cumulative_number_distribution"),
    ("Size Distribution cumulative surface", "size_distribution_cumulative_surface_distribution"),
)


def result_category(dataset: Dataset | GenericCurve) -> str | None:
    """Return the precise saved-result category, if this is one of ours."""
    metadata: Mapping[str, object] = dataset.metadata
    result = metadata.get("bernardyn_result")
    if not isinstance(result, Mapping):
        return None
    analysis = result.get("analysis")
    role = result.get("role")
    if analysis not in {"unified_fit", "size_distribution"} or not isinstance(role, str):
        return None
    return f"{analysis}_{role}"


def matches_dataset_filter(dataset: Dataset | GenericCurve, filter_id: str) -> bool:
    """Whether *dataset* belongs in a selected browser/inspector view."""
    if filter_id == "all":
        return True
    category = result_category(dataset)
    if filter_id == "sas":
        return category is None
    return category == filter_id
