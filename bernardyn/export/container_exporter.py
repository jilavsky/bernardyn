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
import os
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
            pg_widget = self._get_pg_widget(plot_widget)

            # Create HDF5 file
            with h5py.File(output_path, 'w') as f:
                # Write metadata group
                meta_group = f.create_group('metadata')
                meta_group.attrs['version'] = self.CONTAINER_VERSION

                # Detect plot type and export data
                plot_type = self._export_plot_data(f, pg_widget, meta_group)
                meta_group.attrs['plot_type'] = plot_type

                # Write plot state attributes from the plot widget
                self._export_plot_state(pg_widget, meta_group)

            logger.info("Exported project to %s", output_path)
            return True

        except Exception as e:
            logger.error("Failed to export project to %s: %s", output_path, e)
            return False

    def _get_pg_widget(self, plot_widget: Any) -> Any:
        """Extract the underlying pyqtgraph PlotWidget from various widget types."""
        if hasattr(plot_widget, 'get_plot_widget'):
            return plot_widget.get_plot_widget()
        elif hasattr(plot_widget, '_plot_widget'):
            return plot_widget._plot_widget
        return plot_widget

    def _export_plot_data(self, f: Any, pg_widget: Any, meta_group: Any) -> str:
        """Export plot data and return the detected plot type."""
        import numpy as np

        data_group = f.create_group('data')
        plot_items = []

        # Get all data items from the plot widget
        if hasattr(pg_widget, 'listDataItems'):
            plot_items = pg_widget.listDataItems()
        elif hasattr(pg_widget, 'plotItem'):
            plot_items = pg_widget.plotItem.listDataItems()

        # Check for image items
        image_items = []
        if hasattr(pg_widget, 'plotItem'):
            plot_item = pg_widget.plotItem
            for child in plot_item.children if hasattr(plot_item, 'children') else []:
                if hasattr(child, 'glMode') and child.glMode:
                    image_items.append(child)

        # Export line plot data
        if plot_items:
            sas_group = data_group.create_group('sas_data')
            sas_metadata = sas_group.create_group('metadata')

            for i, item in enumerate(plot_items):
                if hasattr(item, 'data') and item.data:
                    data_obj = item.data()
                    if data_obj is not None:
                        x_data = data_obj.x
                        y_data = data_obj.y

                        if x_data is not None and y_data is not None:
                            x_array = np.array(x_data, dtype=np.float64)
                            y_array = np.array(y_data, dtype=np.float64)

                            # Store first item's x as Q
                            if i == 0:
                                sas_group.create_dataset('Q', data=x_array)
                                sas_metadata.attrs['x_label'] = 'Q'
                                sas_metadata.attrs['x_units'] = '[1/A]'

                            # Store y values
                            dataset_name = f'I_{i}' if i > 0 else 'I'
                            sas_group.create_dataset(dataset_name, data=y_array)

                            # Get error bars if available
                            if hasattr(item, 'errorBars'):
                                try:
                                    x_err, y_err = item.errorBars()
                                    if y_err is not None:
                                        y_err_array = np.array(y_err, dtype=np.float64)
                                        err_dataset_name = f'Idev_{i}' if i > 0 else 'Idev'
                                        sas_group.create_dataset(err_dataset_name, data=y_err_array)
                                except (TypeError, AttributeError):
                                    pass

            # Store legend names if available
            self._export_legend_names(sas_group, pg_widget)

        # Export image data if present
        if image_items:
            img_group = data_group.create_group('raw_image')
            for i, img_item in enumerate(image_items):
                if hasattr(img_item, 'glMode') and img_item.glMode:
                    continue  # Skip GL mode items

                if hasattr(img_item, 'getImage'):
                    try:
                        img_data = img_item.getImage()
                        if img_data is not None:
                            img_array = np.array(img_data, dtype=np.float32)
                            dataset_name = f'image_{i}' if i > 0 else 'data'
                            img_group.create_dataset(dataset_name, data=img_array)
                    except (AttributeError, TypeError):
                        pass

                # Store vmin/vmax
                if hasattr(img_item, 'getLevels'):
                    try:
                        vmin, vmax = img_item.getLevels()
                        img_group.attrs['vmin'] = vmin
                        img_group.attrs['vmax'] = vmax
                    except (TypeError, AttributeError):
                        pass

        return 'image' if image_items else ('line' if plot_items else 'empty')

    def _export_legend_names(self, sas_group: Any, pg_widget: Any) -> None:
        """Export legend names as attributes to corresponding datasets."""
        if hasattr(pg_widget, 'legend') and pg_widget.legend:
            legend_items = pg_widget.legend.items if hasattr(pg_widget.legend, 'items') else []
            for i, legend_item in enumerate(legend_items):
                if hasattr(legend_item, 'name') and legend_item.name:
                    name = legend_item.name
                    if isinstance(name, str) and name:
                        # Map legend index to dataset name
                        if i == 0:
                            label_key = 'Q'
                        else:
                            label_key = f'Q_{i}'
                        if label_key in sas_group:
                            sas_group[label_key].attrs['legend_name'] = name

    def _export_plot_state(self, pg_widget: Any, meta_group: Any) -> None:
        """Export plot state (log mode, ranges) to HDF5 metadata."""
        import numpy as np

        # Try to get log mode from the plot widget
        if hasattr(pg_widget, 'getLogMode'):
            try:
                x_log, y_log = pg_widget.getLogMode()
                meta_group.attrs['x_log'] = x_log
                meta_group.attrs['y_log'] = y_log
            except (TypeError, AttributeError):
                meta_group.attrs['x_log'] = False
                meta_group.attrs['y_log'] = False
        else:
            meta_group.attrs['x_log'] = False
            meta_group.attrs['y_log'] = False

        # Export range from the view box
        if hasattr(pg_widget, 'getViewBox'):
            try:
                vb = pg_widget.getViewBox()
                if vb:
                    range_x = vb.state['viewRange'][0] if 'viewRange' in vb.state else (0, 1)
                    range_y = vb.state['viewRange'][1] if 'viewRange' in vb.state else (0, 1)
                    meta_group.attrs['x_range'] = list(range_x)
                    meta_group.attrs['y_range'] = list(range_y)
            except (TypeError, AttributeError, KeyError):
                pass

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

                    # Load range info
                    if 'x_range' in meta_group.attrs:
                        result['metadata']['x_range'] = list(meta_group.attrs['x_range'])
                    if 'y_range' in meta_group.attrs:
                        result['metadata']['y_range'] = list(meta_group.attrs['y_range'])

                # Load data
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
        import numpy as np

        result = {}

        if 'sas_data' in data_group:
            sas_group = data_group['sas_data']
            sas_data = {
                'Q': None,
                'I': None,
                'Idev': None,
                'metadata': {},
            }

            # Load Q dataset
            if 'Q' in sas_group:
                sas_data['Q'] = np.array(sas_group['Q'])

            # Load I dataset
            if 'I' in sas_group:
                sas_data['I'] = np.array(sas_group['I'])

            # Load Idev dataset (error bars)
            if 'Idev' in sas_group:
                sas_data['Idev'] = np.array(sas_group['Idev'])

            # Load metadata
            if 'metadata' in sas_group:
                meta = sas_group['metadata']
                sas_data['metadata']['x_label'] = meta.attrs.get('x_label', 'Q')
                sas_data['metadata']['x_units'] = meta.attrs.get('x_units', '[1/A]')

            # Load additional datasets (multiple curves)
            datasets = list(sas_group.keys())
            for key in datasets:
                if key not in ('Q', 'I', 'Idev') and key != 'metadata':
                    if 'Q_' in key or 'I_' in key:
                        if 'additional' not in sas_data:
                            sas_data['additional'] = {}
                        sas_data['additional'][key] = np.array(sas_group[key])

            result['sas_data'] = sas_data

        if 'raw_image' in data_group:
            img_group = data_group['raw_image']
            img_data = {
                'vmin': img_group.attrs.get('vmin', 0),
                'vmax': img_group.attrs.get('vmax', 1),
                'images': {},
            }

            # Load all image datasets
            for key in img_group.keys():
                if isinstance(img_group[key], h5py.Dataset):
                    img_data['images'][key] = np.array(img_group[key])

            result['raw_image'] = img_data

        return result


# Global container exporter instance
_default_container_exporter = ContainerExporter()


def get_container_exporter() -> ContainerExporter:
    """Get the global container exporter instance."""
    return _default_container_exporter
