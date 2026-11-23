"""Qt is imported only through ``bernardyn.gui._qt`` (house standard)."""

from __future__ import annotations

import ast
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SHIM = ROOT / "bernardyn" / "gui" / "_qt.py"


def _direct_qt_imports(path: Path) -> list[str]:
    """Real ``import`` statements of PySide6/PyQt6 (script text in strings is ignored)."""
    found = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.ImportFrom):
            modules = [node.module or ""]
        elif isinstance(node, ast.Import):
            modules = [alias.name for alias in node.names]
        else:
            continue
        for module in modules:
            if module.split(".")[0] in {"PySide6", "PyQt6", "PyQt5", "PySide2"}:
                found.append(f"{path.relative_to(ROOT)}:{node.lineno} {module}")
    return found


def test_only_the_shim_imports_a_qt_binding():
    files = [*(ROOT / "bernardyn").rglob("*.py"), *(ROOT / "tests").rglob("*.py")]
    offenders = [hit for path in files if path != SHIM for hit in _direct_qt_imports(path)]
    assert offenders == [], "import Qt from bernardyn.gui._qt instead:\n" + "\n".join(offenders)


def test_shim_import_stays_light_and_pins_pyqtgraph():
    # A fresh interpreter: importing the renderers must not load the main
    # window, and PyQtGraph must end up on PySide6.
    code = (
        "import sys, bernardyn.renderers, pyqtgraph.Qt as q;"
        "print(q.QT_LIB, 'bernardyn.gui.main_window' in sys.modules)"
    )
    env = {key: value for key, value in os.environ.items() if key != "PYQTGRAPH_QT_LIB"}
    env.setdefault("QT_QPA_PLATFORM", "offscreen")
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, env=env, cwd=ROOT, check=True
    )
    assert result.stdout.split() == ["PySide6", "False"]
