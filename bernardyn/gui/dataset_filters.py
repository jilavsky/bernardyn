"""Shared dataset-category choices for the browser and graph inspector."""

from __future__ import annotations

from collections.abc import Mapping

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
    ("Size Distribution number distribution", "size_distribution_number_distribution"),
    ("Size Distribution surface distribution", "size_distribution_surface_distribution"),
    ("Size Distribution cumulative volume", "size_distribution_cumulative_volume_distribution"),
    ("Size Distribution cumulative number", "size_distribution_cumulative_number_distribution"),
    ("Size Distribution cumulative surface", "size_distribution_cumulative_surface_distribution"),
    ("Modeling results", "modeling_measured"),
    ("Modeling total fit", "modeling_fit"),
    ("Modeling populations", "modeling_populations"),
    ("Modeling residuals", "modeling_residuals"),
    ("Modeling volume distribution", "modeling_volume_distribution"),
    ("Modeling number distribution", "modeling_number_distribution"),
    ("Simple Fits results", "simple_fits_measured"),
    ("Simple Fits model", "simple_fits_fit"),
    ("Simple Fits residuals", "simple_fits_residuals"),
    ("WAXS Peak Fit results", "waxs_peakfit_measured"),
    ("WAXS Peak Fit model", "waxs_peakfit_fit"),
    ("WAXS Peak Fit background", "waxs_peakfit_background"),
    ("WAXS Peak Fit peaks", "waxs_peakfit_peaks"),
    ("WAXS Peak Fit residuals", "waxs_peakfit_residuals"),
    ("Carbon fitting results", "carbon_fit_measured"),
    ("Carbon fitting model", "carbon_fit_fit"),
    ("Carbon fitting components", "carbon_fit_components"),
    ("Carbon fitting residuals", "carbon_fit_residuals"),
)


def result_category(dataset: Dataset | GenericCurve) -> str | None:
    """Return the precise saved-result category, if this is one of ours."""
    metadata: Mapping[str, object] = dataset.metadata
    result = metadata.get("bernardyn_result")
    if not isinstance(result, Mapping):
        return None
    analysis = result.get("analysis")
    role = result.get("role")
    if analysis not in {
        "unified_fit", "size_distribution", "modeling", "simple_fits",
        "waxs_peakfit", "carbon_fit",
    } or not isinstance(role, str):
        return None
    if analysis == "modeling" and role.startswith("population_"):
        # population_<n> is an I(Q) curve; population_<n>_<kind>_distribution
        # is one population's size distribution.
        for kind in ("volume_distribution", "number_distribution"):
            if role.endswith(kind):
                return f"modeling_{kind}"
        return "modeling_populations"
    if analysis == "waxs_peakfit" and role.startswith("peak_"):
        return "waxs_peakfit_peaks"
    if analysis == "carbon_fit" and role in {"grain_porod", "micropores", "diffraction"}:
        return "carbon_fit_components"
    if role == "residual":
        role = "residuals"
    return f"{analysis}_{role}"


def dataset_category_label(dataset: Dataset | GenericCurve) -> str:
    """Short user-facing category, e.g. "Unified Fit residuals" or "SAS data"."""
    category = result_category(dataset)
    if category is None:
        return "SAS data"
    return next((label for label, filter_id in DATASET_FILTERS if filter_id == category), category)


def matches_dataset_filter(dataset: Dataset | GenericCurve, filter_id: str) -> bool:
    """Whether *dataset* belongs in a selected browser/inspector view."""
    if filter_id == "all":
        return True
    category = result_category(dataset)
    if filter_id == "sas":
        return category is None
    return category == filter_id
