"""Entry point for `python -m noticias`.

Loads environment variables from .env (if present) before any other module
imports, so the LLM client can read API keys when the user runs the CLI.
Library/programmatic use should call load_dotenv() themselves.

The .env file is located by walking up from this file's directory looking
for pyproject.toml, so the lookup is robust to the user's CWD.
"""

from pathlib import Path

from dotenv import load_dotenv


def _find_project_root(start: Path) -> Path:
    """Walk up from `start` until we find a pyproject.toml."""
    current = start.resolve()
    for parent in [current, *current.parents]:
        if (parent / "pyproject.toml").exists():
            return parent
    return start  # fallback: best-effort


_PROJECT_ROOT = _find_project_root(Path(__file__).parent)
load_dotenv(_PROJECT_ROOT / ".env")

from noticias.cli.app import app

app()
