# Headless plot recipes

Bernardyn's public recipe facade creates a validated graph package from existing
data or a saved pyIrena result without opening the desktop main window. Optional
PNG, JPEG, and SVG output uses the same 2-D Qt/PyQtGraph renderer as the desktop
application in an offscreen Qt runtime.

The facade reads inputs only. It does not fit data, edit sources, or execute
arbitrary HDF5 instructions.

## Python

```python
from bernardyn import PlotRequest, Presentation, ScatteringInput, create_plot

result = create_plot(
    PlotRequest(
        recipe_id="porod",
        inputs=(ScatteringInput("sample.h5"),),
        presentation=Presentation(title="Sample Porod", width_px=1600, height_px=1000, dpi=250),
        package_path="sample-porod",
        image_path="sample-porod.png",
    )
)
print(result.package_path)
print(result.diagnostics)
```

Specify `ScatteringInput(..., internal_path="/entry/sasdata")` when a file has
multiple curves and the exact group is known. Omitting it selects the source
adapter's normal primary curve.

For a saved result, use `ResultInput` and one of the registered result recipes:

```python
from bernardyn import PlotRequest, ResultInput, create_plot

result = create_plot(
    PlotRequest(
        recipe_id="size_distribution_volume_distribution",
        result=ResultInput("saved-result.h5", "size_distribution"),
        package_path="distribution",
    )
)
```

Use `list_recipes()` to enumerate stable recipe IDs and `inspect_data(path)` to
discover scattering selections and available saved-result analyses before making
a request.

## Command line

`bernardyn-plot list-recipes` prints the supported recipes. To create a Porod
package and image:

```sh
bernardyn-plot create --recipe porod --input sample.h5 \
  --package sample-porod --image sample-porod.png \
  --width-px 1600 --height-px 1000 --dpi 250
```

For a public pyIrena result curve:

```sh
bernardyn-plot create --recipe unified_fit_residuals --input saved-result.h5 \
  --package residuals
```

Existing output paths are rejected unless `--overwrite` (or `overwrite=True` in
Python) is supplied. The CLI emits a compact JSON result containing artifact
paths and point-count diagnostics.

## Current recipe set

- `raw_iq`, all Guinier variants, `porod`, `kratky`,
  `dimensionless_kratky`, modified Porod, `zimm`, and `debye_bueche` accept
  one or more scattering inputs. `dimensionless_kratky` requires explicit
  `I0` and `Rg` in each `series_parameters` row (or matching source metadata).
- `unified_fit_data_fit` and `size_distribution_data_fit` use saved measured
  data and fit records.
- `unified_fit_residuals` and `size_distribution_residuals` use typed residual
  curves with a linear Y axis.
- `size_distribution_volume_distribution` uses the stored radius centres and
  volume-fraction density; it does not infer histogram widths.
- `size_distribution_cumulative_volume_distribution`,
  `size_distribution_cumulative_number_distribution`, and
  `size_distribution_cumulative_surface_distribution` use their stored
  cumulative arrays without recalculating them.

Recipes preserve the same canonical datasets, transformations, graph package
format, and result semantics as the GUI. Pixel-identical images are not
guaranteed across platforms because fonts and Qt rendering vary, but output
dimensions, DPI, quantities, units, and provenance are recorded.
