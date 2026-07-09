"""Unit tests for the LLM response parser (llm/parser.py).

Covers:
- Valid JSON parses correctly
- JSON with extra prose around it is extracted
- Invalid JSON returns stub
- JSON missing highlights defaults to []
- JSON missing summary defaults to "Resumen no disponible"
"""

from __future__ import annotations

from noticias.llm.parser import parse_batch_llm_response, stub_summary
from noticias.models.cluster import LLMResponse
from tests.helpers import make_cluster


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
