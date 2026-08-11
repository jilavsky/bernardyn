# Extending Bernardyn

This document describes how to extend Bernardyn with new data formats, plot types, and exporters.

## Architecture Overview

Bernardyn follows a modular architecture with clear separation between:
- **Data Loading Layer** (`data/`) — Loads data from various file formats
- **Plotting Engine Layer** (`plot/`) — Renders data as visualizations
- **GUI Layer** (`gui/`) — User interface components
- **Export Layer** (`export/`) — Exports plots to various formats
- **Template System** (`template/`) — Saves/loads plot configurations
- **Utilities** (`utils/`) — Shared helpers

## Adding a New Data Format

To add support for a new file format (e.g., NeXus, FIT2D):

1. **Create a new loader class** in `data/` that extends the abstract `Loader` base class:

```python
from abc import ABC, abstractmethod
from typing import Any, Dict

class MyLoader(ABC):
    """Abstract base class for all data loaders."""

    @abstractmethod
    def can_load(self, filepath: str) -> bool:
        """Check if this loader can handle the given file."""
        ...

    @abstractmethod
    def load(self, filepath: str) -> Dict[str, Any]:
        """Load data from the given file.

        Returns a dict with at least:
          - 'type': str identifying the data type
          - 'filepath': the source file path
        """
        ...
```

2. **Implement the loader** with your format-specific logic:

```python
class MyFormatLoader(MyLoader):
    """Loads data from MyFormat files."""

    SUPPORTED_EXTENSIONS = (".myformat", ".mf")

    def can_load(self, filepath: str) -> bool:
        return any(filepath.lower().endswith(ext) for ext in self.SUPPORTED_EXTENSIONS)

    def load(self, filepath: str) -> Dict[str, Any]:
        # Your format-specific loading logic here
        return {
            "type": "myformat",
            "filepath": filepath,
            # Add your data structure here
        }
```

3. **Register the loader** in `data/loader.py`:

```python
from bernardyn.data.myformat_loader import MyFormatLoader
_default_dispatcher.register(MyFormatLoader())
```

## Adding a New Plot Type

To add a new visualization type (e.g., 3D surface plot):

1. **Create a new plotter class** in `plot/` that extends the abstract `Plotter` base class:

```python
from abc import ABC, abstractmethod
from typing import Any, Dict

class MyPlotter(ABC):
    """Abstract base class for all plotters."""

    @abstractmethod
    def get_plot_type(self) -> str:
        """Return the plot type identifier (e.g., 'surface')."""
        ...

    @abstractmethod
    def get_plot_config(self, **kwargs) -> Dict[str, Any]:
        """Get the rendering configuration for this plotter."""
        ...
```

2. **Implement the plotter** with your rendering logic:

```python
class SurfacePlotter(MyPlotter):
    """Creates 3D surface plots."""

    def get_plot_type(self) -> str:
        return "surface"

    def get_plot_config(self, **kwargs):
        # Your surface rendering configuration here
        return {
            "type": "surface",
            "data": self._surface_data,
            # Add your configuration here
        }
```

3. **Create an adapter** in `plot/plot_engine.py`:

```python
class SurfacePlotterAdapter(Plotter):
    """Adapter that wraps SurfacePlotter as a Plotter interface implementation."""

    def __init__(self, surface_plotter):
        self._plotter = surface_plotter

    def get_plot_type(self) -> str:
        return "surface"

    def get_plot_config(self, **kwargs):
        return self._plotter.get_plot_config(**kwargs)
```

4. **Register the adapter** in `plot/plot_engine.py`:

```python
from bernardyn.plot.surface_plotter import SurfacePlotter, SurfacePlotterAdapter

_default_engine.register(SurfacePlotterAdapter(SurfacePlotter()))
```

5. **Add UI controls** in `gui/controls_panel.py` for the new plot type:

```python
self._plot_type_combo.addItem("Surface Plot", "surface")
```

6. **Add rendering logic** in `gui/main_window.py`:

```python
elif plot_type == "surface":
    self._render_surface_plot(plot_widget, controls)
```

## Adding a New Export Format

To add support for exporting to a new format (e.g., TIFF):

1. **Create a new exporter class** in `export/` that extends the abstract `Exporter` base class:

```python
from abc import ABC, abstractmethod
from typing import Any

class MyExporter(ABC):
    """Abstract base class for all exporters."""

    @abstractmethod
    def get_format_name(self) -> str:
        """Return the format name identifier (e.g., 'tiff')."""
        ...

    @abstractmethod
    def export(self, plot_widget: Any, output_path: str) -> bool:
        """Export the plot to the specified format.

        Args:
            plot_widget: The pyqtgraph PlotWidget to export.
            output_path: Path for the exported file.

        Returns:
            True if export succeeded, False otherwise.
        """
        ...
```

2. **Implement the exporter** with your format-specific logic:

```python
class TiffExporter(MyExporter):
    """Exports plots to TIFF format."""

    def get_format_name(self) -> str:
        return "tiff"

    def export(self, plot_widget: Any, output_path: str) -> bool:
        # Your TIFF export logic here
        return True
```

3. **Register the exporter** in `export/exporter.py`:

```python
from bernardyn.export.tiff_exporter import TiffExporter
_default_dispatcher.register(TiffExporter())
```

## Adding Annotation Support

To add drawing/annotation capabilities to plots:

1. **Create an annotation manager** in `plot/annotations.py`:

```python
class AnnotationManager:
    """Manages annotations on plots (text, arrows, rectangles, etc.)."""

    def __init__(self):
        self._annotations: List[Dict[str, Any]] = []

    def add_text(self, x: float, y: float, text: str) -> None:
        """Add a text annotation."""
        self._annotations.append({
            "type": "text",
            "x": x,
            "y": y,
            "text": text,
        })

    def add_arrow(self, x1: float, y1: float, x2: float, y2: float) -> None:
        """Add an arrow annotation."""
        self._annotations.append({
            "type": "arrow",
            "x1": x1,
            "y1": y1,
            "x2": x2,
            "y2": y2,
        })

    def get_annotations(self) -> List[Dict[str, Any]]:
        """Get all annotations."""
        return list(self._annotations)

    def clear(self) -> None:
        """Clear all annotations."""
        self._annotations = []
```

2. **Integrate with PlotWidget** in `gui/plot_widget.py`:

```python
class PlotWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._annotation_manager = AnnotationManager()

    def add_annotation(self, annotation: Dict[str, Any]) -> None:
        """Add an annotation to the plot."""
        self._annotation_manager.add_annotation(annotation)
        # Render the annotation on the plot

    def clear_annotations(self) -> None:
        """Clear all annotations."""
        self._annotation_manager.clear()
```

## Plugin Points Summary

| Component | Extension Point | Location |
|-----------|----------------|----------|
| Data Loader | `Loader` abstract class | `data/loader.py` |
| Plot Type | `Plotter` abstract class | `plot/plot_engine.py` |
| Export Format | `Exporter` abstract class | `export/exporter.py` |
| Plot Widget | `PlotWidget` class | `gui/plot_widget.py` |
| Controls Panel | `ControlsPanel` class | `gui/controls_panel.py` |
| Template Schema | JSON structure | `template/storage.py` |

## Best Practices

1. **Follow the existing patterns** — Use the abstract base classes and adapter pattern
2. **Keep modules focused** — Each module should have a single responsibility
3. **Use type hints** — All public methods should have type annotations
4. **Write docstrings** — Document all public classes and methods
5. **Add tests** — Include unit tests for new functionality
6. **Handle errors gracefully** — Log errors and return sensible defaults

## Example: Adding a New Data Format (CSV)

Here's a complete example of adding CSV support:

```python
# data/csv_loader.py
import csv
from typing import Any, Dict

class CsvLoader(ABC):
    """Loads data from CSV files."""

    SUPPORTED_EXTENSIONS = (".csv",)

    def can_load(self, filepath: str) -> bool:
        return any(filepath.lower().endswith(ext) for ext in self.SUPPORTED_EXTENSIONS)

    def load(self, filepath: str) -> Dict[str, Any]:
        data = {"type": "csv", "filepath": filepath}

        with open(filepath, 'r') as f:
            reader = csv.reader(f)
            rows = list(reader)

        # Parse CSV data (assuming first row is header)
        if len(rows) > 1:
            headers = rows[0]
            values = [list(map(float, row)) for row in rows[1:]]

            if len(values) >= 2:
                data["x"] = [row[0] for row in values]
                data["y"] = [row[1] for row in values]

        return data
```

Register it:
```python
# data/loader.py
from bernardyn.data.csv_loader import CsvLoader
_default_dispatcher.register(CsvLoader())
```

## Conclusion

Bernardyn's modular architecture makes it easy to extend with new features. By following the patterns described in this document, you can add support for new data formats, plot types, and export formats while maintaining code quality and consistency.
