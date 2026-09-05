# Bernardyn

Bernardyn is a PySide6/PyQtGraph workbench for publication-oriented plotting of
small-angle scattering and diffraction curves. It keeps scientific arrays out
of widgets and stores complete, source-independent graphs in portable HDF5
packages.

## Current capabilities

- Browse all discoverable NXcanSAS/simple-HDF5 entries and 2–4 column text data.
- Keep a workspace-wide dataset catalog and independent graph tabs.
- Plot General I(Q), Guinier, rod/sheet Guinier, Kratky, dimensionless Kratky,
  Porod, modified Porod, Zimm, and Debye–Bueche views.
- Style each curve, errors, labels, axes, legends, typography, and annotations.
- Render 3D line waterfalls and common-grid surfaces with an isolated,
  lazily-loaded PyQtGraph OpenGL backend and 2D fallback.
- Save one graph or a deduplicated multi-graph workspace as
  `*.bernardyn.h5`, including canonical data, resolved snapshots, configuration,
  checksums, previews, and 3D renderer data.
- Export PNG/JPEG/SVG, CSV, Igor ITX, and canonical data through PyIrena's H5XP
  writer. H5XP export is data interoperability, not Bernardyn graph persistence.

The native schema is documented in
[`bernardyn/schemas/graph-package-v1.md`](bernardyn/schemas/graph-package-v1.md).

## Install and run

Bernardyn targets Python 3.10–3.13 and shares its Qt plotting dependencies with
PyIrena. For development, keep the `Bernardyn` and `pyirena` repositories next
to each other and create the pinned Conda environment from the Bernardyn root:

```bash
conda env create -f environment.yml
conda activate bernardyn
bernardyn-doctor
bernardyn
```

The environment file installs both repositories in editable mode. If an older
`bernardyn` environment already exists with Python 3.14, remove and recreate it:

```bash
conda deactivate
conda env remove -n bernardyn
conda env create -f environment.yml
conda activate bernardyn
```

For an already compatible Python 3.10–3.13 environment, installation can also
be performed manually:

```bash
python -m pip install -e "../pyirena[qtplot]"
python -m pip install -e ".[dev]"
bernardyn
```

To diagnose an installation:

```bash
bernardyn-doctor
bernardyn-doctor --json
```

The OpenGL renderer needs a usable graphics context. If it cannot initialize,
Bernardyn displays a 2D offset-waterfall fallback and retains the 3D document
configuration.

## Development

```bash
pytest
ruff check bernardyn tests
python -m build
twine check dist/*
```

Extension entry points are `bernardyn.sources`, `bernardyn.transforms`, and
`bernardyn.renderers`; see [`bernardyn/EXTENDING.md`](bernardyn/EXTENDING.md).

## Scope

Version 1.0 is a plotting and presentation application. Model fitting,
reduction, destructive source modification, movies, and calibrated 2D detector
workflows are intentionally outside 1.0. Existing experimental 0.1 containers
are not treated as compatible graph packages.

Bernardyn is distributed under the MIT License.
