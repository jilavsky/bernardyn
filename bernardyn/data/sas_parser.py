"""NXcanSAS attribute navigation logic for Bernardyn.

Parses HDF5 files following the NXcanSAS standard to locate 1D SAS data.
Also handles NXsas raw detector images and slit-smeared data variants.

Navigation logic (confirmed from LnG_0103.hdf and Rh1_0085.h5):

  root/
    entry/                    NX_class="NXentry", canSAS_class="SASentry"
      {default_attr}/         Group name from "default" attribute (e.g., "LnG")
        sasdata/              NX_class="NXdata", canSAS_class="SASdata"
          I                   signal = "I"  (Intensity, Y data)
          Idev                uncertainties
          Q                   I_axes = "Q"  (scattering vector, X data)
          Qdev                resolutions

  root/entry/data/            NX_class="NXdata", canSAS_class="NXsas"
    data                      2D area detector image

  root/entry/{name}_SMR/sasdata/   Slit-smeared data (optional)
  root/entry/{name}/sasdata/       Desmeared data (optional)
"""

import logging
from typing import Any, Dict, List, Optional, Tuple

import h5py
import numpy as np

logger = logging.getLogger(__name__)


class SasData:
    """Container for parsed 1D SAS data with metadata."""

    def __init__(self):
        self.x: np.ndarray = np.array([])       # X values (e.g., Q)
        self.y: np.ndarray = np.array([])       # Y values (e.g., I)
        self.y_err: Optional[np.ndarray] = None  # Y uncertainties (e.g., Idev)
        self.x_err: Optional[np.ndarray] = None  # X uncertainties (e.g., Qdev)
        self.x_label: str = ""
        self.x_units: str = ""
        self.y_label: str = ""
        self.y_units: str = ""
        self.source_file: str = ""
        self.data_type: str = "SAS"  # "SAS", "slit_smear", or "desmear"
        self.attributes: Dict[str, Any] = {}

    def __repr__(self):
        return (
            f"SasData(x={len(self.x)}pts, y={len(self.y)}pts, "
            f"type={self.data_type}, x_label={self.x_label!r})"
        )


class RawImageData:
    """Container for raw 2D detector image data."""

    def __init__(self):
        self.data: np.ndarray = np.array([])  # 2D array
        self.attributes: Dict[str, Any] = {}

    def __repr__(self):
        if self.data.size > 0:
            return f"RawImageData(shape={self.data.shape}, dtype={self.data.dtype})"
        return "RawImageData(empty)"


def _get_attr(obj: Any, name: str, default: Any = None) -> Any:
    """Safely get an HDF5 attribute, converting bytes to str where appropriate."""
    val = obj.attrs.get(name, default)
    if isinstance(val, bytes):
        return val.decode("utf-8", errors="replace")
    return val


def _get_attr_array(obj: Any, name: str) -> Optional[np.ndarray]:
    """Get an HDF5 attribute as a numpy array."""
    val = obj.attrs.get(name)
    if val is None:
        return None
    return np.asarray(val)


def find_sas_entries(h5file: h5py.File) -> List[str]:
    """Find all NXentry groups that contain SAS data.

    Returns a list of entry group names (e.g., ['entry']).
    """
    entries = []
    for name, obj in h5file.items():
        nx_class = _get_attr(obj, "NX_class", "")
        sas_class = _get_attr(obj, "canSAS_class", "")
        if nx_class == "NXentry" and sas_class == "SASentry":
            entries.append(name)
    return entries


def find_sas_data_group(entry_group: h5py.Group) -> Optional[h5py.Group]:
    """Navigate from an NXentry group to the SAS data group.

    Follows: entry -> {default} -> sasdata
    Returns the sasdata group or None if not found.
    """
    default_name = _get_attr(entry_group, "default")
    if not default_name:
        logger.warning("NXentry has no 'default' attribute")
        return None

    default_group = entry_group.get(default_name)
    if default_group is None:
        logger.warning("Default group '%s' not found in entry", default_name)
        return None

    sas_class = _get_attr(default_group, "canSAS_class", "")
    if sas_class != "SASentry":
        logger.warning(
            "Group '%s' has canSAS_class=%r, expected 'SASentry'",
            default_name, sas_class,
        )
        return None

    sasdata_group = default_group.get("sasdata")
    if sasdata_group is None:
        logger.warning("Group '%s' has no 'sasdata' subgroup", default_name)
        return None

    sas_data_class = _get_attr(sasdata_group, "canSAS_class", "")
    if sas_data_class != "SASdata":
        logger.warning(
            "Group 'sasdata' has canSAS_class=%r, expected 'SASdata'",
            sas_data_class,
        )
        return None

    return sasdata_group


def parse_sas_data(sasdata_group: h5py.Group) -> SasData:
    """Parse 1D SAS data from a sasdata group following NXcanSAS.

    Reads signal (Y), axes (X), uncertainties, and resolutions from attributes.
    """
    result = SasData()

    # Get signal (Y data) name from "signal" attribute
    signal_name = _get_attr(sasdata_group, "signal")
    if not signal_name:
        raise ValueError("sasdata group has no 'signal' attribute")

    signal = sasdata_group[signal_name]
    result.y = np.asarray(signal[:])

    # Read Y metadata
    result.y_label = _get_attr(signal, "long_name", signal_name)
    result.y_units = _get_attr(signal, "units", "")
    result.source_file = _get_attr(signal, "label", "")

    # Get axes (X data) name from "{signal}_axes" attribute
    x_name = _get_attr(sasdata_group, signal_name + "_axes")
    if not x_name:
        raise ValueError(f"sasdata group has no '{signal_name}_axes' attribute")

    x_data = sasdata_group[x_name]
    result.x = np.asarray(x_data[:])

    # Read X metadata
    result.x_label = _get_attr(x_data, "long_name", x_name)
    result.x_units = _get_attr(x_data, "units", "")

    # Read uncertainties (error bars)
    unc_name = _get_attr(signal, "uncertainties")
    if unc_name and unc_name in sasdata_group:
        result.y_err = np.asarray(sasdata_group[unc_name][:])

    # Read resolutions (optional X uncertainties)
    res_name = _get_attr(x_data, "resolutions")
    if res_name and res_name in sasdata_group:
        result.x_err = np.asarray(sasdata_group[res_name][:])

    # Store all group attributes
    result.attributes = dict(sasdata_group.attrs)

    return result


def parse_slit_smear_data(group: h5py.Group) -> Optional[SasData]:
    """Parse slit-smeared SAS data from a group like Rh1_SMR/sasdata.

    Returns None if the group doesn't contain valid SAS data.
    """
    sasdata = group.get("sasdata")
    if sasdata is None:
        return None

    signal_name = _get_attr(sasdata, "signal")
    if not signal_name or signal_name not in sasdata:
        return None

    result = SasData()
    result.data_type = "slit_smear"

    signal = sasdata[signal_name]
    result.y = np.asarray(signal[:])
    result.y_label = _get_attr(signal, "long_name", signal_name)
    result.y_units = _get_attr(signal, "units", "")

    x_name = _get_attr(sasdata, signal_name + "_axes")
    if not x_name or x_name not in sasdata:
        return None

    x_data = sasdata[x_name]
    result.x = np.asarray(x_data[:])
    result.x_label = _get_attr(x_data, "long_name", x_name)
    result.x_units = _get_attr(x_data, "units", "")

    unc_name = _get_attr(signal, "uncertainties")
    if unc_name and unc_name in sasdata:
        result.y_err = np.asarray(sasdata[unc_name][:])

    # Slit-smeared data may have dual resolutions (dQl, dQw)
    # We store the first one found as x_err
    for res_key in ("dQl", "dQw"):
        if res_key in sasdata:
            ds = sasdata[res_key]
            # Handle both scalar and array datasets
            if ds.ndim == 0:
                result.x_err = np.asarray(ds[()])
            else:
                result.x_err = np.asarray(ds[:])
            break

    return result


def find_raw_image(entry_group: h5py.Group) -> Optional[RawImageData]:
    """Find and load the first 2D raw detector image from an NXentry group.

    Looks in root/entry/data/data following NXsas convention.
    Falls back to finding the first 2D dataset in entry/data/.
    """
    data_group = entry_group.get("data")
    if data_group is None:
        return None

    # Try the standard "data" dataset first
    if "data" in data_group:
        img = RawImageData()
        img.data = np.asarray(data_group["data"][:])
        img.attributes = dict(data_group.attrs)
        return img

    # Fallback: find first 2D dataset in data group
    for name, obj in data_group.items():
        if isinstance(obj, h5py.Dataset) and obj.ndim == 2:
            img = RawImageData()
            img.data = np.asarray(obj[:])
            img.attributes = dict(data_group.attrs)
            return img

    return None


def find_slit_smear_groups(entry_group: h5py.Group) -> Tuple[Optional[SasData], Optional[SasData]]:
    """Find slit-smeared and desmeared data in an NXentry group.

    Returns (slit_smear_data, desmear_data) — each may be None.
    Detects groups ending in _SMR as slit-smeared, others as desmeared.
    """
    slit_smear = None
    desmear = None

    for name, obj in entry_group.items():
        if not isinstance(obj, h5py.Group):
            continue

        is_smr = name.endswith("_SMR")
        sasdata = obj.get("sasdata")
        if sasdata is None:
            continue

        signal_name = _get_attr(sasdata, "signal")
        if not signal_name or signal_name not in sasdata:
            continue

        parsed = parse_slit_smear_data(obj) if is_smr else parse_sas_data(sasdata)
        if parsed is None:
            continue

        if is_smr:
            slit_smear = parsed
        else:
            desmear = parsed

    return slit_smear, desmear


def parse_hdf5_file(filepath: str) -> Dict[str, Any]:
    """Parse an HDF5 file and extract all available SAS data.

    Returns a dict with keys:
      - 'sas_entries': list of entry names with SAS data
      - 'sas_data': dict mapping entry name -> SasData (1D)
      - 'raw_image': RawImageData or None (2D)
      - 'slit_smear': SasData or None
      - 'desmear': SasData or None
    """
    result = {
        "sas_entries": [],
        "sas_data": {},
        "raw_image": None,
        "slit_smear": None,
        "desmear": None,
    }

    with h5py.File(filepath, "r") as f:
        entries = find_sas_entries(f)
        result["sas_entries"] = entries

        for entry_name in entries:
            entry_group = f[entry_name]
            sasdata_group = find_sas_data_group(entry_group)
            if sasdata_group is not None:
                result["sas_data"][entry_name] = parse_sas_data(sasdata_group)

        raw_image = find_raw_image(f["entry"])
        if raw_image is not None:
            result["raw_image"] = raw_image

        slit_smear, desmear = find_slit_smear_groups(f["entry"])
        result["slit_smear"] = slit_smear
        result["desmear"] = desmear

    return result
