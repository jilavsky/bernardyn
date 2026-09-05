"""Command-line diagnostics for Bernardyn installations."""

from __future__ import annotations

import argparse
import json
import platform
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
    }
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
        from pyirena.io import discover_scattering, load_scattering  # noqa: F401

        checks["pyirena_shared_api"] = True
    except Exception as exc:
        checks["pyirena_shared_api"] = False
        checks["pyirena_api_error"] = str(exc)
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
        checks["pyirena_shared_api"],
        checks["pyside6"] is not None,
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
        print(f"PyIrena: {result['pyirena'] or 'missing'}")
        print(f"PyIrena shared API: {'ok' if result['pyirena_shared_api'] else 'missing'}")
        print(f"PySide6 / PyQtGraph: {result['pyside6'] or 'missing'} / {result['pyqtgraph'] or 'missing'}")
        print(f"OpenGL 3D: {'ready' if result['three_d_ready'] else result['opengl_message']}")
    return 0 if result["healthy"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
