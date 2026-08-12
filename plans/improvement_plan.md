# Bernardyn Improvement Plan - Bug Fixes & Enhancements

This document outlines identified bugs and proposed improvements for the Bernardyn codebase, to be addressed in a separate session.

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
