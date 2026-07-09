"""Unit tests for config_path() — NOTICIAS_CONFIG_PATH env var support.

Tests the env-var override logic: default path, absolute/relative/tilde paths,
and empty-string fallback.  Each test isolates the env var via monkeypatch.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from noticias.sources.registry import config_path


def test_default_when_env_var_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    """When NOTICIAS_CONFIG_PATH is unset, return ~/.config/noticias/config.json."""
    monkeypatch.delenv("NOTICIAS_CONFIG_PATH", raising=False)
    result = config_path()
    expected = (Path.home() / ".config" / "noticias" / "config.json").resolve()
    assert result == expected


def test_env_var_absolute_path(monkeypatch: pytest.MonkeyPatch) -> None:
    """When NOTICIAS_CONFIG_PATH is absolute, return that path."""
    monkeypatch.setenv("NOTICIAS_CONFIG_PATH", "C:\\Temp\\noticias-test.json")
    result = config_path()
    assert result == Path("C:\\Temp\\noticias-test.json").resolve()


def test_env_var_relative_path_resolved_against_cwd(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When NOTICIAS_CONFIG_PATH is relative, resolve against CWD."""
    monkeypatch.setenv("NOTICIAS_CONFIG_PATH", "noticias-test.json")
    result = config_path()
    assert result.is_absolute()
    assert result.name == "noticias-test.json"
    assert result.parent == Path.cwd().resolve()


def test_env_var_with_tilde_expanded(monkeypatch: pytest.MonkeyPatch) -> None:
    """When NOTICIAS_CONFIG_PATH starts with ~, expand home dir."""
    monkeypatch.setenv("NOTICIAS_CONFIG_PATH", "~/my-config.json")
    result = config_path()
    assert result == (Path.home() / "my-config.json").resolve()


def test_env_var_empty_string_falls_back_to_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When NOTICIAS_CONFIG_PATH is empty, fall back to default path."""
    monkeypatch.setenv("NOTICIAS_CONFIG_PATH", "")
    result = config_path()
    expected = (Path.home() / ".config" / "noticias" / "config.json").resolve()
    assert result == expected
