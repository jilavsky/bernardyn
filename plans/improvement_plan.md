# Bernardyn Improvement Plan - Bug Fixes & Enhancements

This document outlines identified bugs and proposed improvements for the Bernardyn codebase, to be addressed in a separate session.

## 2. Functional Bugs & Incomplete Implementations
These issues affect application behavior and feature completeness without causing immediate crashes.

### A. Stubbed Container Exporter
*   **File**: `bernardyn/export/container_exporter.py`
*   **Issue**: The `export` method is a stub that writes hardcoded metadata to an HDF5 file but ignores the actual plot state and data arrays. The `load` method is similarly incomplete.
*   **Proposed Fix**: Implement full serialization of the current plot configuration (from `ControlsPanel`) and embed the relevant datasets into the HDF5 container.

### B. Silent Plot Clearing on Data Mismatch
*   **File**: `bernardyn/gui/main_window.py`
*   **Issue**: In `_on_graph_generate`, if a plot type (e.g., "image") is selected but no matching data exists in the loaded files, the plot widget is cleared without notifying the user.
*   **Proposed Fix**: Add a `QMessageBox` warning or status bar message when a plot cannot be rendered due to missing compatible data.

### C. Legend Name Loss on Dataset Removal
*   **File**: `bernardyn/gui/controls_panel.py`
*   **Issue**: The `_on_remove_dataset` method clears and rebuilds all legend input fields with default names, erasing any custom labels the user had entered for remaining datasets.
*   **Proposed Fix**: Modify `_on_remove_dataset` to preserve existing text in legend inputs when rebuilding the list.

---

## 3. Minor Issues & Improvements
These are non-critical improvements for code quality and robustness.

### A. Inline Imports in Main Window
*   **File**: `bernardyn/gui/main_window.py`
*   **Issue**: The `_on_graph_update_style` method performs imports (`from bernardyn.plot.plot_style import ...`) inside the function body, which is inefficient for frequently called UI updates.
*   **Proposed Fix**: Move these imports to the top of the file.

### B. Ambiguous Image Export Fallback
*   **File**: `bernardyn/export/image_exporter.py`
*   **Issue**: The fallback case in `export` calls `pixmap.save(output_path)` without specifying a format, relying on the filename extension which may be unreliable or unsupported by the system's default image handler.
*   **Proposed Fix**: Explicitly determine and pass the format to `save()` based on the file extension.
