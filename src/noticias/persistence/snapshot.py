"""Snapshot persistence — write/read/list daily snapshots to/from ``.data/``.

Uses msgspec for serialization. No database. Backward tolerance via Struct
defaults. Idempotent naming: the first run of the day writes
``YYYY-MM-DD.json``; subsequent runs on the same day append
``-HHMMSS`` to avoid clobbering.

Entry points:
    - ``write_snapshot``: persist a ``Snapshot`` to disk.
    - ``read_snapshot``: load a ``Snapshot`` from disk.
    - ``list_snapshots``: list all snapshot files in a directory.
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

import msgspec

from noticias.models.snapshot import Snapshot

logger = logging.getLogger(__name__)


def write_snapshot(snapshot: Snapshot, target_dir: Path) -> Path:
    """Write a snapshot to disk with idempotent naming.

    If ``target_dir / {snapshot.date}.json`` does not exist, that name is
    used.  If it does (second run on the same day), a ``-HHMMSS`` suffix
    is appended to prevent clobbering.

    Args:
        snapshot: The snapshot to write.
        target_dir: The directory to write into (created if missing).

    Returns:
        The path that was written.
    """
    target_dir.mkdir(parents=True, exist_ok=True)

    simple_path = target_dir / f"{snapshot.date}.json"

    if not simple_path.exists():
        path = simple_path
    else:
        now = datetime.now()
        timestamp = now.strftime("%H%M%S")
        path = target_dir / f"{snapshot.date}-{timestamp}.json"

    data = msgspec.json.encode(snapshot)
    path.write_bytes(data)
    logger.info("Snapshot written to %s", path)
    return path


def read_snapshot(path: Path) -> Snapshot:
    """Read a snapshot from disk.

    Args:
        path: The path to the snapshot file.

    Returns:
        The decoded ``Snapshot`` object.

    Raises:
        FileNotFoundError: If the file does not exist.
        ValueError: If the path contains ``..`` traversal components
            (safety net — the CLI also validates).
    """
    if ".." in path.parts:
        raise ValueError(f"Path traversal blocked: {path}")

    return msgspec.json.decode(path.read_bytes(), type=Snapshot)


def list_snapshots(target_dir: Path) -> list[Path]:
    """List all snapshot files in a directory, sorted newest first.

    Only ``.json`` files are considered.  Non-existent directories return
    an empty list (no error).

    Args:
        target_dir: The directory to scan.

    Returns:
        A list of ``Path`` objects sorted by name descending (newest
        first based on date-string ordering).
    """
    if not target_dir.exists():
        return []

    return sorted(
        [p for p in target_dir.iterdir() if p.suffix == ".json" and p.is_file()],
        key=lambda p: p.name,
        reverse=True,
    )
