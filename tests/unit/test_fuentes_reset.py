"""Unit tests for the new `fuentes reset` CLI command."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from noticias.cli.fuentes import fuentes_reset
from noticias.sources.defaults import DEFAULT_SOURCES
from noticias.sources.registry import SourceRegistry


def _write_config(path: Path, sources: list[dict], **extra: object) -> None:
    """Write a config file with the given sources and extras."""
    data = {"version": 1, "sources": sources, **extra}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def test_reset_replaces_sources_with_defaults(tmp_path: Path) -> None:
    cfg_path = tmp_path / "config.json"
    _write_config(
        cfg_path,
        sources=[{
            "name": "infobae",
            "url": "https://www.infobae.com/rss/",
            "lean": "center",
            "last_fetched_status": "never",
            "last_fetched_at": None,
        }],
    )
    with patch("noticias.cli.fuentes.config_path", return_value=cfg_path):
        registry = SourceRegistry()
        fuentes_reset(registry)

    raw = json.loads(cfg_path.read_text(encoding="utf-8"))
    assert [s["name"] for s in raw["sources"]] == [s.name for s in DEFAULT_SOURCES]
    assert len(raw["sources"]) == 5


def test_reset_preserves_other_fields(tmp_path: Path) -> None:
    cfg_path = tmp_path / "config.json"
    _write_config(
        cfg_path,
        sources=[{
            "name": "infobae",
            "url": "https://www.infobae.com/rss/",
            "lean": "center",
            "last_fetched_status": "never",
            "last_fetched_at": None,
        }],
        topics=["economia", "futbol"],
        blocked_keywords=["tarot"],
        model="groq/llama-3.3-70b-versatile",
        token_budget=9000,
    )
    with patch("noticias.cli.fuentes.config_path", return_value=cfg_path):
        registry = SourceRegistry()
        fuentes_reset(registry)

    raw = json.loads(cfg_path.read_text(encoding="utf-8"))
    assert raw["topics"] == ["economia", "futbol"]
    assert raw["blocked_keywords"] == ["tarot"]
    assert raw["model"] == "groq/llama-3.3-70b-versatile"
    assert raw["token_budget"] == 9000
    # Sources replaced
    assert [s["name"] for s in raw["sources"]] == [s.name for s in DEFAULT_SOURCES]


def test_reset_uses_env_var_path_when_set(tmp_path: Path, monkeypatch) -> None:
    """NOTICIAS_CONFIG_PATH drives fuentes_reset read/write target."""
    cfg_path = tmp_path / "env-config.json"
    _write_config(
        cfg_path,
        sources=[{
            "name": "infobae",
            "url": "https://www.infobae.com/rss/",
            "lean": "center",
            "last_fetched_status": "never",
            "last_fetched_at": None,
        }],
    )
    monkeypatch.setenv("NOTICIAS_CONFIG_PATH", str(cfg_path))

    registry = SourceRegistry()
    fuentes_reset(registry)

    raw = json.loads(cfg_path.read_text(encoding="utf-8"))
    assert [s["name"] for s in raw["sources"]] == [s.name for s in DEFAULT_SOURCES]
    assert len(raw["sources"]) == 5
