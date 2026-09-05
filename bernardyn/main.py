"""Backward-compatible module entry point."""

from __future__ import annotations

from bernardyn.app import main

if __name__ == "__main__":
    raise SystemExit(main())
