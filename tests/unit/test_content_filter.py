"""Unit tests for the keyword-based content filter (pipeline/content_filter.py).

Covers:
- Title matches keyword
- Body matches keyword
- Both title and body match
- Neither matches (item survives)
- Case-insensitive matching
- Empty keywords list (passthrough)
- ``None`` keywords (uses module defaults)
- Multi-keyword: only one matches
- Empty items list
"""

from __future__ import annotations

import pytest

from noticias.pipeline.content_filter import _DEFAULT_BLOCKED, filter_content
from tests.helpers import make_item


class TestFilterContent:
    def test_title_matches_keyword(self) -> None:
        """Item with 'Horóscopo' in the title is dropped."""
        items = [make_item(title="Horóscopo de hoy: qué dicen los astros")]
        result = filter_content(items, blocked=["horóscopo"])
        assert result == []

    def test_body_matches_keyword(self) -> None:
        """Item with 'Gran Hermano' in the body is dropped."""
        items = [
            make_item(
                title="Resumen de la noche",
                body="Anoche en Gran Hermano pasaron cosas increíbles.",
            ),
        ]
        result = filter_content(items, blocked=["Gran Hermano"])
        assert result == []

    def test_both_title_and_body_match(self) -> None:
        """Item matching in both fields is still dropped once."""
        items = [
            make_item(
                title="Gran Hermano: la gala de esta noche",
                body="Gran Hermano continúa con su temporada.",
            ),
        ]
        result = filter_content(items, blocked=["Gran Hermano"])
        assert result == []

    def test_no_match_survives(self) -> None:
        """Item with no keywords survives the filter."""
        items = [
            make_item(
                title="Economía argentina crece",
                body="El PBI subió 3% este trimestre.",
            ),
        ]
        result = filter_content(items, blocked=["horóscopo"])
        assert len(result) == 1
        assert result[0].title == "Economía argentina crece"

    def test_case_insensitive(self) -> None:
        """Keywords match regardless of case."""
        items = [
            make_item(title="HOROSCOPO de hoy"),
            make_item(title="horoscopo de la semana"),
            make_item(title="Horoscopo semanal"),
        ]
        result = filter_content(items, blocked=["horóscopo"])
        assert result == []

    def test_empty_keywords_passthrough(self) -> None:
        """Empty keywords list passes all items through unchanged."""
        items = [
            make_item(title="Horóscopo de hoy"),
            make_item(title="Noticia importante"),
        ]
        result = filter_content(items, blocked=[])
        assert len(result) == 2

    def test_none_uses_defaults(self) -> None:
        """``None`` keywords uses ``_DEFAULT_BLOCKED``."""
        items = [make_item(title="Horóscopo de hoy")]
        result = filter_content(items, blocked=None)
        assert result == []

    def test_none_uses_defaults_blocked_list(self) -> None:
        """Verify the default list actually contains the expected keywords."""
        assert "Gran Hermano" in _DEFAULT_BLOCKED
        assert "farándula" in _DEFAULT_BLOCKED

    def test_multi_keyword_one_matches(self) -> None:
        """Item matching any single keyword is dropped."""
        items = [
            make_item(title="Billboard: los más escuchados"),
            make_item(title="Política internacional hoy"),
        ]
        result = filter_content(items, blocked=["Billboard", "farándula"])
        assert len(result) == 1
        assert result[0].title == "Política internacional hoy"

    def test_empty_items(self) -> None:
        """Empty items list returns empty list."""
        result = filter_content([], blocked=["horóscopo"])
        assert result == []

    def test_no_items_with_none_keywords(self) -> None:
        """Empty items list with default keywords returns empty list."""
        result = filter_content([], blocked=None)
        assert result == []
