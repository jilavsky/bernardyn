"""Command-line diagnostics for Bernardyn installations."""

from __future__ import annotations

import argparse
import importlib
import json
import platform
import re
import sys
import tempfile
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any

import h5py
import numpy as np

from bernardyn import __version__


def _version(name: str) -> str | None:
    try:
        return version(name)
    except PackageNotFoundError:
        return None


# The pyIrena floor from pyproject.toml (a test keeps the two equal).  It is
# not read from installed metadata, which an old editable install leaves stale.
MINIMUM_PYIRENA = "1.2.0"
_PRE_RELEASE_ORDER = {"a": 0, "b": 1, "rc": 2}


def _version_key(text: str) -> tuple:
    """Order release numbers such as 1.2.0b2 < 1.2.0rc1 < 1.2.0 < 1.2.1.

    Handles the version styles used by this project and its dependencies
    without adding the ``packaging`` dependency.  Unparseable text sorts low.
    """
    match = re.match(r"(\d+(?:\.\d+)*)(?:\.?(a|b|rc)(\d+))?", text.strip())
    if match is None:
        return ((), (-1, 0))
    release = tuple(int(part) for part in match.group(1).split("."))
    release += (0,) * (3 - len(release))
    pre = (_PRE_RELEASE_ORDER[match.group(2)], int(match.group(3))) if match.group(2) else (3, 0)
    return (release, pre)


def _pyside6_supported(text: str | None) -> bool:
    # 6.9.1 renders empty plots; 6.10.* is excluded by pyirena[qtplot].
    return text is not None and text != "6.9.1" and not text.startswith("6.10.")


def diagnose() -> dict[str, Any]:
    checks: dict[str, Any] = {
        "bernardyn": __version__,
        "python": platform.python_version(),
        "supported_python": (3, 10) <= sys.version_info[:2] < (3, 14),
        "numpy": np.__version__,
        "h5py": h5py.__version__,
        "pyirena": _version("pyirena"),
        "pyside6": _version("PySide6"),
        "pyqtgraph": _version("pyqtgraph"),
        "pyopengl": _version("PyOpenGL"),
        "platform": platform.platform(),
        "mcp": _version("mcp"),
    }
    checks["pyirena_minimum"] = MINIMUM_PYIRENA
    checks["pyirena_meets_minimum"] = checks["pyirena"] is not None and (
        _version_key(checks["pyirena"]) >= _version_key(checks["pyirena_minimum"])
    )
    checks["pyside6_supported"] = _pyside6_supported(checks["pyside6"])
    try:
        with tempfile.TemporaryDirectory(prefix="bernardyn-doctor-") as folder:
            path = Path(folder) / "probe.h5"
            with h5py.File(path, "w") as handle:
                handle["probe"] = np.arange(3, dtype=float)
            with h5py.File(path, "r") as handle:
                checks["hdf5_round_trip"] = bool(np.array_equal(handle["probe"][:], [0, 1, 2]))
    except Exception as exc:
        checks["hdf5_round_trip"] = False
        checks["hdf5_error"] = str(exc)
    try:
        # Import the implementation first.  PyIrena's package facade treats a
        # missing optional dependency as an empty API, which otherwise hides
        # the actionable dependency error from the user.
        importlib.import_module("pyirena.io.scattering")
        from pyirena.io import discover_scattering, load_scattering  # noqa: F401

        checks["pyirena_shared_api"] = True
    except Exception as exc:
        checks["pyirena_shared_api"] = False
        checks["pyirena_api_error"] = str(exc)
    try:
        from pyirena.io.schema import TOOL_REGISTRY

        expected = {
            "unified_fit", "size_distribution", "modeling", "simple_fits",
            "waxs_peakfit", "carbon_fit",
        }
        checks["pyirena_plot_results"] = expected.issubset(TOOL_REGISTRY)
        if not checks["pyirena_plot_results"]:
            checks["pyirena_plot_results_error"] = (
                f"missing HDF5 schemas: {', '.join(sorted(expected - TOOL_REGISTRY.keys()))}"
            )
    except Exception as exc:
        checks["pyirena_plot_results"] = False
        checks["pyirena_plot_results_error"] = str(exc)
    try:
        from bernardyn.renderers.opengl import opengl_available

        checks["opengl_available"], checks["opengl_message"] = opengl_available()
    except Exception as exc:
        checks["opengl_available"] = False
        checks["opengl_message"] = str(exc)
    required = (
        checks["supported_python"],
        checks["hdf5_round_trip"],
        checks["pyirena"] is not None,
        checks["pyirena_meets_minimum"],
        checks["pyirena_shared_api"],
        checks["pyirena_plot_results"],
        checks["pyside6_supported"],
        checks["pyqtgraph"] is not None,
    )
    checks["healthy"] = all(required)
    checks["three_d_ready"] = bool(checks["opengl_available"])
    return checks


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check Bernardyn's scientific and Qt runtime")
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    options = parser.parse_args(argv)
    result = diagnose()
    if options.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(f"Bernardyn {result['bernardyn']} on Python {result['python']}")
        print(f"Core runtime: {'ready' if result['healthy'] else 'incomplete'}")
        print(f"HDF5 round-trip: {'ok' if result['hdf5_round_trip'] else 'failed'}")
        print(f"PyIrena: {result['pyirena'] or 'missing'} (requires >= {result['pyirena_minimum']})")
        if result["pyirena"] and not result["pyirena_meets_minimum"]:
            print(
                "  Installed pyIrena metadata is older than required. Upgrade it with "
                "python -m pip install -U pyirena, or reinstall an editable checkout with "
                "python -m pip install -e <path to pyirena>."
            )
        print(f"PyIrena shared API: {'ok' if result['pyirena_shared_api'] else 'missing'}")
        print(f"PyIrena plottable results: {'ok' if result['pyirena_plot_results'] else 'missing'}")
        if not result["pyirena_plot_results"]:
            print(f"  {result.get('pyirena_plot_results_error', 'required result schema is missing')}")
        if not result["pyirena_shared_api"]:
            print(f"  {result.get('pyirena_api_error', 'no import detail available')}")
            if "No module named 'six'" in result.get("pyirena_api_error", ""):
                print("  Repair: python -m pip install six")
        print(f"PySide6 / PyQtGraph: {result['pyside6'] or 'missing'} / {result['pyqtgraph'] or 'missing'}")
        if result["pyside6"] and not result["pyside6_supported"]:
            print("  This PySide6 release is excluded (6.9.1 draws empty plots; 6.10.x is unsupported).")
        print(
            f"MCP server (optional): {result['mcp'] or 'not installed'}"
            + ("" if result["mcp"] else " — install with python -m pip install 'bernardyn[mcp]'")
        )
        print(f"OpenGL 3D: {'ready' if result['three_d_ready'] else result['opengl_message']}")
    return 0 if result["healthy"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
