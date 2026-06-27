"""Helpers to locate project paths from the installed package.

Used by `noticias.__main__` and `noticias.cli.app` to load the `.env` file
from a stable location (the project root) instead of the current working
directory. This makes the CLI work correctly when invoked from any cwd.
"""

from __future__ import annotations

from pathlib import Path


def project_root() -> Path:
    """Return the project root (the directory that contains pyproject.toml).

    Walks up from this file's directory until pyproject.toml is found.
    Falls back to the file's parent if not found (e.g. for non-editable
    installs where pyproject.toml is not adjacent to the package).
    """
    current = Path(__file__).resolve().parent
    for parent in [current, *current.parents]:
        if (parent / "pyproject.toml").exists():
            return parent
    return current
