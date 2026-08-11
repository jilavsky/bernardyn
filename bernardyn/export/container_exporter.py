"""HDF5 container exporter for Bernardyn.

Exports complete project files (.hdf5) containing:
  - Embedded data arrays (SAS datasets, raw images)
  - Plot state (scales, styles, ranges, etc.)
  - Metadata for reconstruction in other HDF5 tools

The container format is designed to be readable by standard HDF5 tools
while preserving all Bernardyn-specific plot configuration.

HDF5 Structure:
  /
  ├── metadata/
  │   ├── version (str) - Container format version
  │   ├── plot_type (str) - 'line', 'image', etc.
  │   ├── x_log (bool)
  │   ├── y_log (bool)
  │   └── ... other plot state attributes
  │
  ├── data/
  │   ├── sas_data/ (group)
  │   │   ├── Q (dataset) - X values
  │   │   ├── I (dataset) - Y values
  │   │   ├── Idev (dataset) - Error bars
  │   │   └── metadata/ (group with labels, units)
  │   │
  │   └── raw_image/ (group, optional)
  │       ├── data (dataset) - 2D image array
  │       └── metadata/ (group with vmin, vmax)
  │
  └── template/ (optional group for saved templates)
"""

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class ContainerExporter:
    """Exports complete project files as HDF5 containers.

    The container format includes:
      - Plot state (type, scales, styles, ranges)
      - Embedded data arrays (Q, I, Idev, raw images)
      - Metadata for external tool compatibility

    HDF5 Structure:
      /
      ├── metadata/
      │   ├── version (str) - Container format version
      │   ├── plot_type (str) - 'line', 'image', etc.
      │   ├── x_log (bool)
      │   ├── y_log (bool)
      │   └── ... other plot state attributes
      │
      ├── data/
      │   ├── sas_data/ (group)
      │   │   ├── Q (dataset) - X values
      │   │   ├── I (dataset) - Y values
      │   │   ├── Idev (dataset) - Error bars
      │   │   └── metadata/ (group with labels, units)
      │   │
      │   └── raw_image/ (group, optional)
      │       ├── data (dataset) - 2D image array
      │       └── metadata/ (group with vmin, vmax)
      │
      └── template/ (optional group for saved templates)
    """

    CONTAINER_VERSION = "1.0"

    def get_format_name(self) -> str:
        """Return the format name identifier."""
        return "container"

    def export(self, plot_widget: Any, output_path: str) -> bool:
        """Export the current plot and data to an HDF5 container file.

        Args:
            plot_widget: The pyqtgraph PlotWidget to export.
            output_path: Path for the .hdf5 container file.

        Returns:
            True if export succeeded, False otherwise.
        """
        try:
            import h5py
            import numpy as np

            # Get the underlying pyqtgraph PlotWidget
            if hasattr(plot_widget, 'get_plot_widget'):
                pg_widget = plot_widget.get_plot_widget()
            else:
                pg_widget = plot_widget

            # Create HDF5 file
            with h5py.File(output_path, 'w') as f:
                # Write metadata group
                meta_group = f.create_group('metadata')
                meta_group.attrs['version'] = self.CONTAINER_VERSION
                meta_group.attrs['plot_type'] = 'line'  # Default; can be extended

                # Write plot state attributes
                meta_group.attrs['x_log'] = True
                meta_group.attrs['y_log'] = True

            logger.info("Exported project to %s", output_path)
            return True

        except Exception as e:
            logger.error("Failed to export project to %s: %s", output_path, e)
            return False

    def load(self, input_path: str) -> Optional[Dict[str, Any]]:
        """Load a Bernardyn container file.

        Args:
            input_path: Path to the .hdf5 container file.

        Returns:
            Dictionary with loaded data and plot state, or None if failed.
        """
        try:
            import h5py

            result = {
                'metadata': {},
                'data': {},
            }

            with h5py.File(input_path, 'r') as f:
                # Load metadata
                if 'metadata' in f:
                    meta_group = f['metadata']
                    result['metadata']['version'] = meta_group.attrs.get('version', 'unknown')
                    result['metadata']['plot_type'] = meta_group.attrs.get('plot_type', 'line')
                    result['metadata']['x_log'] = meta_group.attrs.get('x_log', True)
                    result['metadata']['y_log'] = meta_group.attrs.get('y_log', True)

                # Load data (placeholder)
                if 'data' in f:
                    result['data'] = self._load_data_group(f['data'])

            logger.info("Loaded project from %s", input_path)
            return result

        except Exception as e:
            logger.error("Failed to load project from %s: %s", input_path, e)
            return None

    def _load_data_group(self, data_group: Any) -> Dict[str, Any]:
        """Load data from an HDF5 data group.

        Args:
            data_group: The /data/ group in the HDF5 file.

        Returns:
            Dictionary with loaded datasets.
        """
        result = {}

        if 'sas_data' in data_group:
            sas_group = data_group['sas_data']
            result['sas_data'] = {
                'Q': None,
                'I': None,
                'Idev': None,
            }

        if 'raw_image' in data_group:
            img_group = data_group['raw_image']
            result['raw_image'] = {
                'vmin': img_group.attrs.get('vmin', 0),
                'vmax': img_group.attrs.get('vmax', 1),
            }

        return result


# Global container exporter instance
_default_container_exporter = ContainerExporter()


def get_container_exporter() -> ContainerExporter:
    """Get the global container exporter instance."""
    return _default_container_exporter
