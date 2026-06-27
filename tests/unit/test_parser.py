"""Unit tests for the LLM response parser (llm/parser.py).

Covers:
- Valid JSON parses correctly
- JSON with extra prose around it is extracted
- Invalid JSON returns stub
- JSON missing highlights defaults to []
- JSON missing summary defaults to "Resumen no disponible"
"""

from __future__ import annotations

import pytest

from noticias.llm.parser import parse_batch_llm_response, parse_llm_response, stub_summary
from noticias.models.cluster import LLMResponse
from tests.helpers import make_cluster


class TestParseLLMResponse:
    def test_valid_json_parses_correctly(self) -> None:
        raw = '{"cluster_id": "test", "summary": "A summary.", "highlights": ["Point 1", "Point 2"]}'
        result = parse_llm_response(raw, cluster_id="test")
        assert isinstance(result, LLMResponse)
        assert result.cluster_id == "test"
        assert result.summary == "A summary."
        assert result.highlights == ["Point 1", "Point 2"]

    def test_json_with_prose_extracted(self) -> None:
        """LLM wraps JSON in markdown code block or explanatory text."""
        raw = """Here is the summary you requested:
        {"cluster_id": "test", "summary": "Extracted summary.", "highlights": ["Point"]}
        I hope this helps."""
        result = parse_llm_response(raw, cluster_id="test")
        assert result.summary == "Extracted summary."
        assert result.highlights == ["Point"]

    def test_json_with_only_braces_extracted(self) -> None:
        """Extract JSON from text with only {} pattern."""
        raw = "Some text before. {\"cluster_id\": \"a\", \"summary\": \"Found.\", \"highlights\": []} trailing text."
        result = parse_llm_response(raw, cluster_id="a")
        assert result.summary == "Found."

    def test_invalid_json_returns_stub(self) -> None:
        raw = "This is not valid JSON at all."
        result = parse_llm_response(raw, cluster_id="x")
        assert result.summary == "Resumen no disponible"
        assert result.highlights == []
        assert result.cluster_id == "x"

    def test_missing_highlights_defaults_empty(self) -> None:
        raw = '{"cluster_id": "t", "summary": "No highlights field."}'
        result = parse_llm_response(raw, cluster_id="t")
        assert result.summary == "No highlights field."
        assert result.highlights == []

    def test_missing_summary_defaults(self) -> None:
        raw = '{"cluster_id": "t", "highlights": ["Only highlights"]}'
        result = parse_llm_response(raw, cluster_id="t")
        assert result.summary == "Resumen no disponible"
        assert result.highlights == ["Only highlights"]

    def test_empty_string_returns_stub(self) -> None:
        result = parse_llm_response("", cluster_id="e")
        assert result.summary == "Resumen no disponible"

    def test_none_highlights_defaults_empty(self) -> None:
        raw = '{"cluster_id": "t", "summary": "S", "highlights": null}'
        result = parse_llm_response(raw, cluster_id="t")
        assert result.summary == "S"
        assert result.highlights == []  # null becomes empty due to get() default

    def test_incorrect_json_structure_returns_stub(self) -> None:
        """Valid JSON but wrong structure (not a dict at top level)."""
        raw = '["not", "a", "dict"]'
        result = parse_llm_response(raw, cluster_id="t")
        assert result.summary == "Resumen no disponible"


class TestParseBatchLLMResponse:
    """Tests for ``parse_batch_llm_response`` — batch JSON parser."""

    def test_valid_batch_response(self) -> None:
        raw = (
            '{"clusters": ['
            '{"cluster_id": "a", "summary": "Sum A", "highlights": ["H1"]},'
            '{"cluster_id": "b", "summary": "Sum B", "highlights": ["H2", "H3"]}'
            "]}"
        )
        result = parse_batch_llm_response(raw)
        assert len(result) == 2
        assert result["a"].summary == "Sum A"
        assert result["a"].highlights == ["H1"]
        assert result["b"].summary == "Sum B"
        assert result["b"].highlights == ["H2", "H3"]

    def test_invalid_json_returns_empty(self) -> None:
        result = parse_batch_llm_response("not json at all")
        assert result == {}

    def test_missing_clusters_key_returns_empty(self) -> None:
        raw = '{"summary": "single format", "highlights": []}'
        result = parse_batch_llm_response(raw)
        assert result == {}

    def test_clusters_not_a_list_returns_empty(self) -> None:
        raw = '{"clusters": "not_a_list"}'
        result = parse_batch_llm_response(raw)
        assert result == {}

    def test_skips_entries_without_cluster_id(self) -> None:
        raw = (
            '{"clusters": ['
            '{"summary": "no id"},'
            '{"cluster_id": "ok", "summary": "valid", "highlights": ["H"]}'
            "]}"
        )
        result = parse_batch_llm_response(raw)
        assert "ok" in result
        assert len(result) == 1

    def test_json_extracted_from_prose(self) -> None:
        raw = (
            "Here's the summary:\n"
            '{"clusters": [{"cluster_id": "c", "summary": "S", "highlights": []}]}\n'
            "Hope this helps."
        )
        result = parse_batch_llm_response(raw)
        assert result["c"].summary == "S"

    def test_handles_empty_clusters_list(self) -> None:
        raw = '{"clusters": []}'
        result = parse_batch_llm_response(raw)
        assert result == {}

    def test_missing_fields_use_defaults(self) -> None:
        raw = (
            '{"clusters": ['
            '{"cluster_id": "x"},'
            '{"cluster_id": "y", "highlights": null}'
            "]}"
        )
        result = parse_batch_llm_response(raw)
        assert result["x"].summary == "Resumen no disponible"
        assert result["x"].highlights == []
        assert result["y"].highlights == []


class TestStubSummary:
    def test_stub_summary_returns_llm_response(self) -> None:
        cluster = make_cluster(event_label="Test Event")
        result = stub_summary(cluster)
        assert isinstance(result, LLMResponse)
        assert result.cluster_id == "Test Event"
        assert "sin LLM" in result.summary or "sin LLM" in result.summary.lower()

    def test_stub_summary_neutral_spanish(self) -> None:
        """Stub summary must NOT contain voseo forms."""
        cluster = make_cluster()
        result = stub_summary(cluster)
        for voseo in ("Usá", "Agregá", "Configurá", "Andá", "Poné"):
            assert voseo not in result.summary, (
                f"Found voseo form '{voseo}' in stub summary"
            )

    def test_stub_summary_empty_highlights(self) -> None:
        cluster = make_cluster()
        result = stub_summary(cluster)
        assert result.highlights == []

    def test_stub_summary_uses_cluster_label(self) -> None:
        cluster = make_cluster(event_label="Specific Event Label")
        result = stub_summary(cluster)
        assert result.cluster_id == "Specific Event Label"
