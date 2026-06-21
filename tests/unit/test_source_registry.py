"""Unit tests for SourceRegistry (sources/registry.py).

Covers:
- add / remove / list / get
- Explicit duplicate-name validation (raises ValueError with right message)
- Not-found remove raises ValueError
- save / load round-trip with msgspec
- default() classmethod on missing config file
"""

from __future__ import annotations

from pathlib import Path

import pytest

from noticias.models.source import Lean, Source
from noticias.sources.registry import SourceRegistry


@pytest.fixture
def registry() -> SourceRegistry:
    """A fresh registry with 2 pre-loaded sources."""
    reg = SourceRegistry()
    reg.add(Source(name="pagina12", url="https://www.pagina12.com.ar/rss/portada", lean=Lean.LEFT))
    reg.add(Source(name="infobae", url="https://www.infobae.com/rss/", lean=Lean.CENTER))
    return reg


class TestSourceRegistry:
    def test_list_empty(self) -> None:
        reg = SourceRegistry()
        assert reg.list() == []

    def test_add_and_list(self, registry: SourceRegistry) -> None:
        sources = registry.list()
        assert len(sources) == 2
        names = {s.name for s in sources}
        assert names == {"pagina12", "infobae"}

    def test_add_duplicate_raises(self, registry: SourceRegistry) -> None:
        """Explicit duplicate-name validation: raises ValueError with name."""
        dup = Source(name="pagina12", url="https://www.pagina12.com.ar/rss/portada", lean=Lean.LEFT)
        with pytest.raises(ValueError) as exc:
            registry.add(dup)
        assert "pagina12" in str(exc.value)
        assert "already exists" in str(exc.value)

    def test_add_duplicate_does_not_modify(self, registry: SourceRegistry) -> None:
        """Adding a duplicate leaves the existing source unchanged."""
        dup = Source(name="pagina12", url="https://evil.com/rss", lean=Lean.RIGHT)
        with pytest.raises(ValueError):
            registry.add(dup)
        # The original is unchanged
        sources = registry.list()
        original = [s for s in sources if s.name == "pagina12"][0]
        assert original.url == "https://www.pagina12.com.ar/rss/portada"
        assert original.lean == Lean.LEFT

    def test_remove_existing(self, registry: SourceRegistry) -> None:
        registry.remove("pagina12")
        names = {s.name for s in registry.list()}
        assert names == {"infobae"}

    def test_remove_not_found_raises(self, registry: SourceRegistry) -> None:
        with pytest.raises(ValueError) as exc:
            registry.remove("cronista")
        assert "cronista" in str(exc.value)
        assert "not found" in str(exc.value)

    def test_get_existing(self, registry: SourceRegistry) -> None:
        source = registry.get("pagina12")
        assert source.name == "pagina12"
        assert source.lean == Lean.LEFT

    def test_get_not_found_raises(self, registry: SourceRegistry) -> None:
        with pytest.raises(ValueError) as exc:
            registry.get("missing-source")
        assert "missing-source" in str(exc.value)

    def test_save_load_roundtrip(self, registry: SourceRegistry, tmp_path: Path) -> None:
        path = tmp_path / "config.json"
        registry.save(path)

        loaded = SourceRegistry.load(path)
        assert len(loaded.list()) == 2
        assert loaded.get("pagina12").lean == Lean.LEFT
        assert loaded.get("infobae").lean == Lean.CENTER

    def test_load_missing_file(self, tmp_path: Path) -> None:
        """Loading a non-existent path returns an empty registry."""
        path = tmp_path / "nonexistent.json"
        reg = SourceRegistry.load(path)
        assert reg.list() == []

    def test_save_creates_parent_dirs(self, registry: SourceRegistry, tmp_path: Path) -> None:
        """save() creates parent directories automatically."""
        path = tmp_path / "deep" / "nested" / "config.json"
        registry.save(path)
        assert path.exists()

    def test_default_on_missing_file(self) -> None:
        """default() returns empty registry when ~/.config/noticias/config.json doesn't exist."""
        reg = SourceRegistry.default()
        assert isinstance(reg, SourceRegistry)
        # We can't assert it's empty because the user might have an actual config file,
        # but we can assert it doesn't crash.
        assert isinstance(reg.list(), list)

    def test_list_returns_copy(self, registry: SourceRegistry) -> None:
        """list() returns a copy, not the internal list."""
        sources = registry.list()
        sources.clear()
        assert len(registry.list()) == 2  # original unchanged
