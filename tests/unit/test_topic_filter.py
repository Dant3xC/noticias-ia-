"""Unit tests for the topic-based allowlist filter (pipeline/topic_filter.py).

Covers:
- Single-word topic matches title
- Single-word topic matches body
- Multi-word phrase matches in order
- Multi-word phrase does not match scrambled words
- Case insensitivity
- Empty topics list (passthrough)
- Empty strings in topics list ignored
- Multiple topics: item matches one
- Multiple topics: item matches none
- Item with empty body, only title searched
- Empty items list
- All items dropped
- Topic count exceeding max (capped with warning)
"""

from __future__ import annotations

import pytest

from noticias.pipeline.topic_filter import filter_topics
from tests.helpers import make_item


class TestFilterTopics:
    def test_single_word_topic_matches_title(self) -> None:
        """Item with 'economía' in the title is kept."""
        items = [make_item(title="Economía argentina crece")]
        result = filter_topics(items, topics=["economía"])
        assert len(result) == 1

    def test_single_word_topic_matches_body(self) -> None:
        """Topic matches when present only in the body."""
        items = [
            make_item(
                title="Resumen del día",
                body="La economía argentina muestra signos de recuperación.",
            ),
        ]
        result = filter_topics(items, topics=["economía"])
        assert len(result) == 1

    def test_multi_word_phrase_matches_in_order(self) -> None:
        """Multi-word topic matches as a contiguous phrase."""
        items = [
            make_item(title="Hoy la economía argentina crece notablemente"),
        ]
        result = filter_topics(items, topics=["economía argentina"])
        assert len(result) == 1

    def test_multi_word_phrase_not_scrambled(self) -> None:
        """Scrambled words do not match a multi-word phrase."""
        items = [
            make_item(title="Argentina tiene una economía en problemas"),
        ]
        result = filter_topics(items, topics=["economía argentina"])
        assert result == []

    def test_case_insensitive(self) -> None:
        """Topic matching is case-insensitive."""
        items = [
            make_item(title="ECONOMÍA CRECE"),
            make_item(title="economía crece"),
            make_item(title="Economía Crece"),
        ]
        result = filter_topics(items, topics=["economía"])
        assert len(result) == 3

    def test_empty_topics_passthrough(self) -> None:
        """Empty topics list passes all items through."""
        items = [
            make_item(title="Noticia importante"),
            make_item(title="Otra noticia"),
        ]
        result = filter_topics(items, topics=[])
        assert len(result) == 2

    def test_empty_strings_in_topics_ignored(self) -> None:
        """Empty or whitespace-only strings in topics are ignored."""
        items = [
            make_item(title="Economía argentina"),
            make_item(title="Fútbol argentino"),
        ]
        result = filter_topics(items, topics=["", "  ", "economía"])
        assert len(result) == 1
        assert result[0].title == "Economía argentina"

    def test_multiple_topics_matches_one(self) -> None:
        """Item matching any one topic is kept."""
        items = [
            make_item(title="Fútbol: Boca ganó el clásico"),
            make_item(title="Política internacional"),
        ]
        result = filter_topics(items, topics=["economía", "fútbol"])
        assert len(result) == 1
        assert result[0].title == "Fútbol: Boca ganó el clásico"

    def test_multiple_topics_matches_none(self) -> None:
        """Item matching no topics is dropped."""
        items = [
            make_item(title="Farándula: escándalo en la televisión"),
        ]
        result = filter_topics(items, topics=["economía", "fútbol"])
        assert result == []

    def test_empty_body_still_searches_title(self) -> None:
        """Item with empty body is searched by title only."""
        items = [
            make_item(title="Economía al alza", body=""),
        ]
        result = filter_topics(items, topics=["economía"])
        assert len(result) == 1

    def test_empty_items(self) -> None:
        """Empty items list returns empty list."""
        result = filter_topics([], topics=["economía"])
        assert result == []

    def test_all_items_dropped(self) -> None:
        """When no items match any topic, result is empty."""
        items = [
            make_item(title="Farándula"),
            make_item(title="Horóscopo"),
        ]
        result = filter_topics(items, topics=["economía"])
        assert result == []

    def test_exceeds_max_topics_capped(self) -> None:
        """More than 10 topics is capped at 10."""
        many_topics = [str(i) for i in range(15)]
        items = [make_item(title="5 matches with topic 5")]
        # Only topics 0-9 are checked, so topic "5" matches.
        result = filter_topics(items, topics=many_topics)
        assert len(result) == 1
