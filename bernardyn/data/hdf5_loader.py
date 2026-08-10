"""HDF5 file loader for Bernardyn.

Loads SAS data from HDF5 files following NXcanSAS and NXsas standards.
"""

import logging
from typing import Any, Dict, List, Optional, Tuple, Union

import h5py
import numpy as np

from bernardyn.data.sas_parser import (
    RawImageData,
    SasData,
    parse_hdf5_file,
)

logger = logging.getLogger(__name__)


class Hdf5Loader:
    """Loads SAS data from HDF5 files.

    Supports:
      - NXcanSAS 1D line data (Q vs I with error bars)
      - NXsas 2D raw detector images
      - Slit-smeared and desmeared data variants
    """

    SUPPORTED_EXTENSIONS = (".hdf", ".h5", ".hdf5")

    def can_load(self, filepath: str) -> bool:
        """Check if this loader can handle the given file."""
        return any(filepath.lower().endswith(ext) for ext in self.SUPPORTED_EXTENSIONS)

    def load(self, filepath: str) -> Dict[str, Any]:
        """Load all available data from an HDF5 file.

        Returns a dict with:
          - 'type': 'hdf5'
          - 'filepath': the file path
          - 'sas_data_list': list of SasData objects (1D)
          - 'raw_image': RawImageData or None (2D)
          - 'slit_smear': SasData or None
          - 'desmear': SasData or None
          - 'sas_entries': list of entry names found
        """
        parsed = parse_hdf5_file(filepath)

        sas_data_list = list(parsed["sas_data"].values())
        if not sas_data_list:
            logger.warning("No SAS data found in %s", filepath)

        return {
            "type": "hdf5",
            "filepath": filepath,
            "sas_data_list": sas_data_list,
            "raw_image": parsed["raw_image"],
            "slit_smear": parsed["slit_smear"],
            "desmear": parsed["desmear"],
            "sas_entries": parsed["sas_entries"],
        }

    def load_1d(self, filepath: str) -> Optional[SasData]:
        """Load the first available 1D SAS dataset from an HDF5 file.

        Returns None if no 1D data is found.
        """
        result = self.load(filepath)
        if result["sas_data_list"]:
            return result["sas_data_list"][0]
        return None

    def load_2d(self, filepath: str) -> Optional[RawImageData]:
        """Load the first available 2D raw image from an HDF5 file.

        Returns None if no 2D data is found.
        """
        result = self.load(filepath)
        return result["raw_image"]

    def has_slit_smear(self, filepath: str) -> bool:
        """Check if the file contains slit-smeared data."""
        result = self.load(filepath)
        return result["slit_smear"] is not None

    def has_desmear(self, filepath: str) -> bool:
        """Check if the file contains desmeared data."""
        result = self.load(filepath)
        return result["desmear"] is not None

    def get_data_type(self, filepath: str) -> str:
        """Determine the data type of an HDF5 file.

        Returns one of: '1d_sas', '2d_image', 'slit_smear', 'desmear', 'unknown'
        """
        result = self.load(filepath)

        if result["slit_smear"] is not None:
            return "slit_smear"
        if result["desmear"] is not None:
            return "desmear"
        if result["sas_data_list"]:
            return "1d_sas"
        if result["raw_image"] is not None:
            return "2d_image"
        return "unknown"
