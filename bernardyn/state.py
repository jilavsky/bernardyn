"""Small, development-friendly user state stored outside graph packages."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


class UserState:
    """Persist non-scientific UI choices in ``~/.bernardyn/state.json``.

    This state is intentionally separate from portable graph packages. A bad
    or manually edited file is treated as an empty state rather than blocking
    application startup.
    """

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path) if path is not None else Path.home() / ".bernardyn" / "state.json"
        self.values: dict[str, Any] = self._read()

    def _read(self) -> dict[str, Any]:
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        return value if isinstance(value, dict) else {}

    def get(self, key: str, default: Any = None) -> Any:
        return self.values.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self.values[key] = value

    def save(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.path.with_suffix(".tmp")
            temporary.write_text(json.dumps(self.values, indent=2, sort_keys=True), encoding="utf-8")
            os.replace(temporary, self.path)
        except OSError:
            # Preferences must never prevent opening or saving scientific data.
            return
