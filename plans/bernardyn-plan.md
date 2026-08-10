# Bernardyn - Detailed Implementation Plan

## System Overview

Bernardyn is a PySide6 + pyqtgraph-based plotting application for Small Angle Scattering (SAS) data. The system follows a modular architecture with clear separation between data loading, plotting engine, and GUI layers to support future extensibility.

```
┌─────────────────────────────────────────────────────────────┐
│                        GUI Layer                            │
│  ┌──────────────────┐         ┌─────────────────────────┐  │
│  │ Data Selector    │         │ Plot Controls Panel     │  │
│  │ (Left Panel)     │         │ (Right Panel)           │  │
│  ├──────────────────┤         ├─────────────────────────┤  │
│  │ - Folder browser │         │ - Plot type selector    │  │
│  │ - File listbox   │         │ - Line/style controls   │  │
│  │ - Sort/filter    │         │ - Axis/scale controls   │  │
│  │ - Regex filter   │         │ - Template manager      │  │
│  └────────┬─────────┘         └────────────┬────────────┘  │
│           │                                 │               │
│           └───────────┬─────────────────────┘               │
│                       ▼                                     │
│  ┌─────────────────────────────────────────────────────┐   │
│  │              Main Plot Area (pyqtgraph)             │   │
│  └─────────────────────────────────────────────────────┘   │
├─────────────────────────────────────────────────────────────┤
│                    Controller Layer                         │
│  ┌──────────────────┐  ┌─────────────────────────────┐    │
│  │ Plot Controller  │  │ Template Manager            │    │
│  │ - Coordinates    │  │ - Save/Load/Rename/Delete   │    │
│  │   GUI ↔ Engine   │  │ - Template application      │    │
│  └────────┬─────────┘  └──────────────┬──────────────┘    │
│           │                           │                     │
├───────────┼───────────────────────────┼─────────────────────┤
│           ▼                           ▼                     │
│  ┌──────────────────┐         ┌─────────────────────┐     │
│  │ Plotting Engine  │         │ Data Loading Layer  │     │
│  │ - Line plots     │         │ - HDF5 (NXcanSAS)   │     │
│  │ - Error bars     │         │ - HDF5 (NXsas/2D)   │     │
│  │ - Waterfall      │         │ - ASCII (.txt/.csv) │     │
│  │ - 2D color maps  │         │ - Template files    │     │
│  │ - Image display  │         └─────────────────────┘     │
│  └──────────────────┘                                      │
├─────────────────────────────────────────────────────────────┤
│                    Export Layer                             │
│  ┌──────────┐ ┌─────────┐ ┌──────┐ ┌──────────────────┐  │
│  │ Clipboard│ │ PNG/JPG │ │ SVG  │ │ Bernardyn .h5    │  │
│  │ (Ctrl+C) │ │ Export  │ │ Exp. │ │ Container format │  │
│  └──────────┘ └─────────┘ └──────┘ └──────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

---

## Module Structure

```
bernardyn/
├── __init__.py                    # Package version info
├── main.py                        # Application entry point, MainWindow
├── app.py                         # QApplication setup, lifecycle management
│
├── data/                          # Data loading layer
│   ├── __init__.py
│   ├── loader.py                  # Abstract base + dispatcher for loaders
│   ├── hdf5_loader.py             # HDF5 file loading (NXcanSAS + NXsas)
│   ├── ascii_loader.py            # .txt/.csv loading (2-3 column)
│   └── sas_parser.py              # NXcanSAS attribute navigation logic
│
├── plot/                          # Plotting engine layer
│   ├── __init__.py
│   ├── plot_engine.py             # Abstract base + dispatcher for plot types
│   ├── line_plotter.py            # Line plots, error bars, log/lin scales
│   ├── waterfall_plotter.py       # 3D waterfall plots (order as Z axis)
│   ├── heatmap_plotter.py         # 2D color map plots (order as Y, intensity as color)
│   ├── image_plotter.py           # 2D area detector image display
│   └── plot_style.py              # Color palettes, symbol definitions, line styles
│
├── gui/                           # GUI layer
│   ├── __init__.py
│   ├── main_window.py             # MainWindow with split panel layout
│   ├── data_panel.py              # Left panel: file browser, listbox, sort/filter
│   ├── controls_panel.py          # Right panel: plot type, styles, axes, templates
│   ├── template_dialog.py         # Template management dialog (CRUD)
│   └── plot_widget.py             # pyqtgraph-based plot display widget
│
├── template/                      # Template management layer
│   ├── __init__.py
│   ├── manager.py                 # Save/load/rename/delete templates
│   └── storage.py                 # Template serialization (JSON + embedded data)
│
├── export/                        # Export layer
│   ├── __init__.py
│   ├── exporter.py                # Abstract base + dispatcher for export formats
│   ├── clipboard_exporter.py      # Ctrl/Cmd+C copy to clipboard
│   ├── image_exporter.py          # PNG/JPG/SVG file export
│   └── container_exporter.py      # Bernardyn .h5 container format (data + state)
│
└── utils/                         # Shared utilities
    ├── __init__.py
    ├── file_utils.py              # File naming, regex parsing, sorting helpers
    └── state_manager.py           # Persistent state (last folder, preferences)
```

---

## Data Navigation: NXcanSAS Path Resolution

Based on specifications and confirmed HDF5 file inspection, the navigation logic is:

### 1D SAS Data (NXcanSAS) — Confirmed from `LnG_0103.hdf`

```
root/
└── entry/                    (NX_class = "NXentry", canSAS_class = "SASentry")
    └── {default_attr}/       (e.g., "LnG" — group name from default attribute)
        └── sasdata/          (NX_class = "NXdata", canSAS_class = "SASdata")
            ├── I             (signal = "I", Y data — Intensity)
            │   ├── label     → filename source ("LnG_0103.hdf")
            │   ├── long_name → "Intensity"
            │   ├── uncertainties → "Idev" (error bar source)
            │   └── units     → "[cm2/cm3]"
            ├── Idev          (uncertainties, same units as I)
            ├── Q             (I_axes = "Q", X data — scattering vector)
            │   ├── long_name → "Q (A^-1)"
            │   └── units     → "1/angstrom"
            └── Qdev          (resolutions, optional X uncertainty)
                ├── long_name → "Q (A^-1)"
                └── units     → "1/angstrom"
```

### 2D Raw Image (NXsas) — Confirmed from `LnG_0103.hdf`

```
root/entry/data/              (NX_class = "NXdata", canSAS_class = "NXsas")
└── data                      (2D area detector image, shape varies)
```

### Slit-Smeared Data — Confirmed from `Rh1_0085.h5`

```
root/entry/Rh1_SMR/sasdata/   (NX_class = "NXdata", canSAS_class = "SASdata")
├── I                         (slit-smeared Intensity)
├── Idev                      (uncertainties)
├── Q                         (scattering vector)
├── dQl                       (long resolution)
└── dQw                       (wide resolution)

root/entry/Rh1/sasdata/       (NX_class = "NXdata", canSAS_class = "SASdata")
├── I                         (desmeared Intensity)
├── Idev                      (uncertainties)
├── Q                         (scattering vector)
└── Qdev                      (resolutions)
```

**GUI control**: Slit-smeared/desmeared toggle enabled only when both `Rh1_SMR` and `Rh1` groups exist in the file.

---

## Phased Implementation Plan

### Phase 1: Foundation — Core Data Loading & Basic Plotting
**Goal**: Load data from HDF5 and ASCII files, display a basic line plot.

| Step | Task | Module | Test Criteria |
|------|------|--------|---------------|
| 1.1 | Implement `sas_parser.py` — NXcanSAS attribute navigation logic | `data/sas_parser.py` | Unit test: Given `LnG_0103.hdf`, extract (Q, I, Idev) arrays with correct attributes |
| 1.2 | Implement `hdf5_loader.py` — HDF5 file loading (NXcanSAS + NXsas) | `data/hdf5_loader.py` | Unit test: Load 1D SAS data from LnG_0103.hdf; Load 2D image from root/entry/data/data |
| 1.3 | Implement `ascii_loader.py` — .txt/.csv loading (2-3 column) | `data/ascii_loader.py` | Unit test: Parse 2-column and 3-column files, handle headers/comments |
| 1.4 | Implement `loader.py` — Abstract base + file extension dispatcher | `data/loader.py` | Unit test: Dispatcher routes .hdf/.h5 to HDF5 loader, .txt/.csv to ASCII loader |
| 1.5 | Implement `plot_style.py` — Color palettes, symbol definitions, line styles | `plot/plot_style.py` | Unit test: Generate N distinct colors; map symbol/style names to pyqtgraph objects |
| 1.6 | Implement `line_plotter.py` — Line plots with error bars, log/lin scales | `plot/line_plotter.py` | Integration test: Plot Q vs I with error bars in log-log; verify axes labels and scales |
| 1.7 | Implement `image_plotter.py` — 2D area detector image display with color scales | `plot/image_plotter.py` | Integration test: Display 2D image from LnG_0103.hdf with linear and log color scales |
| 1.8 | Implement `plot_engine.py` — Abstract base + plot type dispatcher | `plot/plot_engine.py` | Unit test: Dispatcher routes "line", "image" to correct plotter; handles scale combinations |

**Phase 1 Deliverable**: Command-line script that loads HDF5/ASCII data and generates line plots or image displays. No GUI yet — pure engine validation.

---

### Phase 2: Core GUI — Main Window with Data Selector & Basic Plot Display
**Goal**: Functional GUI where user can browse files, select datasets, and see plots.

| Step | Task | Module | Test Criteria |
|------|------|--------|---------------|
| 2.1 | Implement `file_utils.py` — File naming regex parsing, sorting helpers | `utils/file_utils.py` | Unit test: Extract order number from "LnG_0103.hdf" → 103; Parse "MIN" for time, "DEG" for temperature |
| 2.2 | Implement `state_manager.py` — Persistent state (last folder, preferences) | `utils/state_manager.py` | Unit test: Save/load last data folder; persists across app restarts |
| 2.3 | Implement `plot_widget.py` — pyqtgraph-based plot display widget | `gui/plot_widget.py` | Unit test: Widget renders line plot; responds to scale changes (log/lin); displays error bars |
| 2.4 | Implement `data_panel.py` — Left panel: folder browser, file listbox, sort/filter | `gui/data_panel.py` | Integration test: Browse to testData/; list files; sort alphabetically and by order number; regex filter works |
| 2.5 | Implement `main_window.py` — MainWindow with split panel layout | `gui/main_window.py` | Integration test: Split window shows data_panel (left) + plot_widget (center); selecting file loads and displays plot |
| 2.6 | Wire data loading to GUI — Selection → Load → Plot pipeline | `gui/` integration | Integration test: Select HDF5 file → auto-detect 1D vs 2D → display correct plot type |

**Phase 2 Deliverable**: Functional GUI with file browsing, dataset selection, and basic plot rendering. User can load HDF5 or ASCII files and see plots.

---

### Phase 3: Plot Controls — Full Styling & Multi-Plot Support
**Goal**: Right panel with complete plot customization controls.

| Step | Task | Module | Test Criteria |
|------|------|--------|---------------|
| 3.1 | Implement `controls_panel.py` — Plot type selector (line, waterfall, heatmap) | `gui/controls_panel.py` | Unit test: Switching plot type changes rendering; controls update based on selection |
| 3.2 | Implement line/style controls — Color, symbol type/size, line style per dataset | `gui/controls_panel.py` | Integration test: Change color/symbol for selected dataset → plot updates in real-time |
| 3.3 | Implement axis controls — Scale (log/lin per axis), range, labels | `gui/controls_panel.py` | Integration test: Set log-log → plot rescales; custom axis labels apply correctly |
| 3.4 | Implement multi-dataset overlay — Multiple datasets on one plot with distinct styles | `plot/line_plotter.py` + GUI | Integration test: Select 5 files → all plotted with different colors/symbols; legend displays correctly |
| 3.5 | Implement grid toggle, legend toggle controls | `gui/controls_panel.py` | Integration test: Toggle grid → appears/disappears; toggle legend → shows/hides |
| 3.6 | Implement slit-smeared data control — Enable when file has both SMR and desmeared data | `gui/controls_panel.py` + `data/hdf5_loader.py` | Integration test: Open Rh1_0085.h5 → SMR/desmeared toggle appears; switching data updates plot |
| 3.7 | Implement multi-graph support — Generate multiple graphs from same dataset selection | `gui/main_window.py` | Integration test: Select 10 files → create 3 graphs with different plot types simultaneously |

**Phase 3 Deliverable**: Full-featured plotting GUI. User can customize every visual aspect, overlay multiple datasets, and manage multiple graphs.

---

### Phase 4: Advanced Plot Types — Waterfall & Heatmap
**Goal**: Support for waterfall plots and 2D color map representations.

| Step | Task | Module | Test Criteria |
|------|------|--------|---------------|
| 4.1 | Implement `waterfall_plotter.py` — 3D waterfall plots (order number as Z offset) | `plot/waterfall_plotter.py` | Unit test: Plot N datasets with Z-offset; verify correct spacing and labeling |
| 4.2 | Implement `heatmap_plotter.py` — 2D color map (X horizontal, order vertical, intensity as color) | `plot/heatmap_plotter.py` | Unit test: Generate heatmap from N datasets; colorbar maps to intensity range correctly |
| 4.3 | Add plot type controls in `controls_panel.py` for waterfall/heatmap options | `gui/controls_panel.py` | Integration test: Select waterfall → controls show Z-offset, rotation; select heatmap → colorbar options appear |
| 4.4 | Implement multi-color-scale support for image plots | `plot/image_plotter.py` + GUI | Integration test: Switch between 5+ color scales (jet, viridis, grayscale, etc.); colorbar updates |

**Phase 4 Deliverable**: All plot types functional. User can choose between line, waterfall, heatmap, and image display modes.

---

### Phase 5: Template System
**Goal**: Save, load, manage plot templates for reuse.

| Step | Task | Module | Test Criteria |
|------|------|--------|---------------|
| 5.1 | Design template schema — What to capture (plot type, scales, styles, axis ranges, size) | `template/` design | Document: Template JSON schema with all configurable properties |
| 5.2 | Implement `storage.py` — Template serialization/deserialization (JSON) | `template/storage.py` | Unit test: Serialize plot state → JSON; deserialize back → identical visual output |
| 5.3 | Implement `manager.py` — Save/load/rename/delete template operations | `template/manager.py` | Unit test: Save template → file created; load template → state restored; rename/delete work correctly |
| 5.4 | Implement `template_dialog.py` — Template management UI (CRUD interface) | `gui/template_dialog.py` | Integration test: Open template dialog → list templates; create/rename/delete operations work |
| 5.5 | Integrate template selector into `controls_panel.py` — Dropdown to apply templates | `gui/controls_panel.py` | Integration test: Select template from dropdown → plot updates to match saved state |
| 5.6 | Implement "Save Current as Template" workflow in controls panel | `gui/controls_panel.py` + template manager | Integration test: Modify plot → save as template → reload template → identical state restored |

**Phase 5 Deliverable**: Complete template system. User can save plot configurations, manage them via dialog, and apply saved templates to new data.

---

### Phase 6: Export System
**Goal**: Multiple export formats for generated plots.

| Step | Task | Module | Test Criteria |
|------|------|--------|---------------|
| 6.1 | Implement `exporter.py` — Abstract base + export format dispatcher | `export/exporter.py` | Unit test: Dispatcher routes "png", "svg", "clipboard" to correct exporter |
| 6.2 | Implement `image_exporter.py` — PNG/JPG/SVG file export with resolution control | `export/image_exporter.py` | Integration test: Export plot → verify file created with correct format and dimensions |
| 6.3 | Implement `clipboard_exporter.py` — Ctrl/Cmd+C copy to clipboard | `export/clipboard_exporter.py` + GUI binding | Integration test: Ctrl+C → paste into document → image appears correctly |
| 6.4 | Design Bernardyn container format (.hdf5) — Data + plot state packaging | `export/container_exporter.py` design | Document: HDF5 structure for container (datasets + attributes for all plot state; data stored in usable form for other tools) |
| 6.5 | Implement `container_exporter.py` — Save/load Bernardyn .hdf5 container files | `export/container_exporter.py` | Integration test: Save plot as .hdf5 → reload in Bernardyn → identical plot with all data restored; verify other HDF5 tools can read the data arrays |
| 6.6 | Wire export actions to menu bar / toolbar (File → Export As, Save Project) | `gui/main_window.py` | Integration test: Menu actions trigger correct export dialogs; files saved to chosen location |

**Phase 6 Deliverable**: Full export system. User can save plots as images, copy to clipboard, or save complete project files as `.hdf5` with embedded data and state. Data stored in usable form so users can open the `.hdf5` in other HDF5-capable tools to plot independently.

---

### Phase 7: Polish, Extensibility & Future-Proofing
**Goal**: Code quality, documentation, and architecture validation for future features.

| Step | Task | Module | Test Criteria |
|------|------|--------|---------------|
| 7.1 | Code review — Verify all modules follow separation of concerns principle | All modules | Architecture review: Adding a new data format requires only adding a loader; no GUI changes needed |
| 7.2 | Add plugin points — Document extension API for new plot types and data formats | `plot/`, `data/` | Documentation: New developer can add a plot type by implementing the abstract base class |
| 7.3 | Implement drawing/annotation support on plots (future-ready interface) | `plot/` extension point | Design: Annotation system with add/remove/move capabilities (deferred implementation) |
| 7.4 | Add comprehensive docstrings and inline documentation | All modules | Documentation: Each public method has docstring; architecture decisions documented in `planning/` |
| 7.5 | Performance testing — Large dataset handling (100+ datasets, high-resolution images) | All modules | Performance test: 50-dataset waterfall plot renders in <2 seconds; image display is responsive |
| 7.6 | Cross-platform testing — macOS, Linux, Windows | All modules | Testing: Application runs and functions identically on all three platforms |

---

## Key Design Decisions & Open Questions

### Decision Log

| # | Decision | Rationale |
|---|----------|-----------|
| D1 | **pyqtgraph for plotting** (already in deps) | Purpose-built for scientific data; fast rendering; supports log scales, error bars, images natively |
| D2 | **PySide6 for GUI** (already in deps) | Modern Qt binding; consistent cross-platform behavior; good integration with pyqtgraph |
| D3 | **JSON for template storage** | Human-readable; easy to debug; versionable in git if needed. Templates stored at `~/.bernardyn/templates/` by default |
| D4 | **HDF5 container for project files (`.hdf5`)** | Standard HDF5 format readable by other tools; embeds actual data arrays + metadata compactly in usable form |
| D5 | **Abstract base classes for loaders/plotters/exporters** | Enables adding new formats (e.g., NeXus, FIT2D) without modifying existing code |
| D6 | **Template schema captures all visual state, not data references** | Templates are about *how* to plot; data paths stored separately in container files |
| D7 | **Default plot type for SAS data is log-log** | SAS community standard; applied automatically on file load |
| D8 | **Multi-dataset auto-styling** | Auto-assign distinct colors and symbols; user can override per-line. Default tested and refined later |
| D9 | **Waterfall Z-offset auto-scales by default** | User-adjustable slider for fine-tuning; sensible defaults for immediate use |
| D10 | **Regex filter persists across sessions** | Remember last filter used; stored in `state_manager.py` |
| D11 | **2D image fallback to first 2D dataset** | Consistent with existing codebase; logical single-fallback behavior |
| D12 | **Template CRUD + import/export** | Templates can be deleted, copied, and imported for cross-machine migration |

### Resolved Questions

| # | Question | Answer |
|---|----------|--------|
| Q1 | **Template storage location** | Default `~/.bernardyn/templates/`; support delete, copy, and import for migration |
| Q2 | **Container file extension** | `.hdf5` — standard HDF5 readable by other tools; data stored in usable form for external plotting |
| Q3 | **Default plot type** | log-log for SAS 1D data (confirmed) |
| Q4 | **Multi-dataset auto-styling** | Auto-assign distinct colors/symbols; refine defaults later |
| Q5 | **Waterfall Z-offset** | Auto-scale default with user-adjustable controls (confirmed) |
| Q6 | **Regex filter persistence** | Persist across sessions (confirmed) |
| Q7 | **2D image fallback** | Fall back to first 2D dataset found (confirmed) |

---

## Testing Strategy Summary

```
Phase 1: Unit tests for data loaders and plot engine (no GUI)
    ↓ Validate core logic in isolation
Phase 2: Integration tests for data → plot pipeline via GUI
    ↓ Validate file loading and basic rendering work together
Phase 3: Manual evaluation + targeted tests for plot controls
    ↓ User evaluates visual quality and control responsiveness
Phase 4: Integration tests for advanced plot types
    ↓ Validate waterfall/heatmap rendering correctness
Phase 5: CRUD tests for template system
    ↓ Validate save/load/rename/delete round-trips
Phase 6: Export format validation tests
    ↓ Validate each export produces correct output files
Phase 7: Performance and cross-platform validation
    ↓ Ensure production readiness
```

---

## Conda Environment Setup

Create the conda environment before starting implementation:

```bash
conda env create -f plans/conda-env.yml
conda activate bernardyn
```

### conda-env.yml contents:

```yaml
name: bernardyn
channels:
  - conda-forge
  - defaults
dependencies:
  - python>=3.10
  - pip
  - numpy>=1.26.0
  - h5py>=3.10.0
  - pyqtgraph>=0.13.0
  - pyside6>=6.6.0
```

After creating the environment, activate it and install the package in development mode:

```bash
cd /Users/ilavsky/GitHub/Bernardyn
pip install -e .
```

## HDF5 File Inspection Script

To inspect the test HDF5 files, create a Python script `inspect_hdf5.py` in the project root with this content:

```python
import h5py
import numpy as np


def explore(name, obj, depth=0):
    indent = "  " * depth
    if isinstance(obj, h5py.Group):
        print("{}GROUP: {}".format(name, name))
        for k, v in obj.attrs.items():
            print("{}  ATTR: {} = {}".format(indent, k, v))
        for key in obj.keys():
            explore(name + "/" + key, obj[key], depth + 1)
    elif isinstance(obj, h5py.Dataset):
        print("{}DATASET: {}".format(indent, name))
        for k, v in obj.attrs.items():
            print("{}  ATTR: {} = {}".format(indent, k, v))
        print("{}  SHAPE: {}, DTYPE: {}".format(indent, obj.shape, obj.dtype))
        if obj.ndim <= 2 and obj.size < 100:
            print("{}  DATA: {}".format(indent, np.array(obj)))


for f in ["testData/LnG_0103.hdf", "testData/Rh1_0085.h5"]:
    print("")
    print("=" * 60)
    print("FILE: " + f)
    print("=" * 60)
    with h5py.File(f, "r") as f:
        explore("root", f)
```

Run it with:

```bash
conda activate bernardyn
python inspect_hdf5.py
```

Paste the output back so we can refine the NXcanSAS navigation logic in Phase 1.

## Recommended Execution Order

1. **Phase 1** → Validate data loading and plotting engine independently (fastest feedback on core logic)
2. **Phase 2** → Build GUI skeleton and wire up data loading (tangible UI progress)
3. **Phase 3** → Add full controls and multi-dataset support (main user workflow)
4. **Phase 4** → Advanced plot types (differentiated features)
5. **Phase 5** → Template system (workflow efficiency)
6. **Phase 6** → Export system (sharing and persistence)
7. **Phase 7** → Polish and extensibility validation (long-term maintainability)

Each phase ends with a clear evaluation point where you can test, provide feedback, and adjust before proceeding.
