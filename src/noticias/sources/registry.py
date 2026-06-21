"""SourceRegistry — CRUD for news sources with JSON persistence.

The registry wraps a SourceConfig, provides explicit validation for
duplicate-name and not-found errors, and persists to disk via msgspec.
"""

from __future__ import annotations

from pathlib import Path

import msgspec

from noticias.models.source import Source, SourceConfig


class SourceRegistry:
    """Manages the list of configured news sources.

    Validation:
    - add(): rejects duplicate names explicitly (reviewer recommendation:
      explicit ValueError, not dict-key collision)
    - remove(): rejects missing names with explicit error
    """

    def __init__(self, config: SourceConfig | None = None) -> None:
        self._config = config or SourceConfig()

    def list(self) -> list[Source]:
        """Return a copy of all configured sources."""
        return list(self._config.sources)

    def add(self, source: Source) -> None:
        """Add a source. Raises ValueError if the name already exists."""
        for existing in self._config.sources:
            if existing.name == source.name:
                raise ValueError(f"source '{source.name}' already exists")
        self._config.sources.append(source)

    def remove(self, name: str) -> None:
        """Remove a source by name. Raises ValueError if not found."""
        idx: int | None = None
        for i, existing in enumerate(self._config.sources):
            if existing.name == name:
                idx = i
                break
        if idx is None:
            raise ValueError(f"source '{name}' not found")
        self._config.sources.pop(idx)

    def get(self, name: str) -> Source:
        """Look up a source by name. Raises ValueError if not found."""
        for source in self._config.sources:
            if source.name == name:
                return source
        raise ValueError(f"source '{name}' not found")

    def save(self, path: Path) -> None:
        """Persist the registry to a JSON file via msgspec."""
        path.parent.mkdir(parents=True, exist_ok=True)
        data = msgspec.json.encode(self._config)
        path.write_bytes(data)

    @classmethod
    def load(cls, path: Path) -> SourceRegistry:
        """Load a registry from a JSON file. Returns empty if file missing."""
        if not path.exists():
            return cls()
        data = path.read_bytes()
        config = msgspec.json.decode(data, type=SourceConfig)
        return cls(config=config)

    @classmethod
    def default(cls) -> SourceRegistry:
        """Load the user's default config file (~/.config/noticias/config.json).

        Returns an empty registry (zero sources) if the file does not exist.
        """
        path = Path.home() / ".config" / "noticias" / "config.json"
        return cls.load(path)
