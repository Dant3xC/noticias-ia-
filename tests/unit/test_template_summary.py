"""Unit tests for template and stub summary helpers.

Covers:
- template_summary(cluster) returns neutral Spanish string
- stub_summary(cluster) returns neutral Spanish string
- Strings do NOT use voseo
"""

from __future__ import annotations

from noticias.llm.client import template_summary
from noticias.llm.parser import stub_summary
from tests.helpers import make_cluster

# List of voseo imperative forms that MUST NOT appear in user-facing strings.
_VOSEO_FORMS = [
    "Usá", "usá",
    "Agregá", "agregá",
    "Configurá", "configurá",
    "Andá", "andá",
    "Poné", "poné",
    "Hacé", "hacé",
    "Decí", "decí",
    "Tomá", "tomá",
    "Vení", "vení",
    "Probá", "probá",
    "Escribí", "escribí",
    "Ingresá", "ingresá",
]


class TestTemplateSummary:
    """template_summary in client.py returns neutral Spanish."""

    def test_returns_string(self) -> None:
        cluster = make_cluster(event_label="Test")
        result = template_summary(cluster)
        assert isinstance(result, str)
        assert len(result) > 10

    def test_no_voseo(self) -> None:
        cluster = make_cluster()
        result = template_summary(cluster)
        for voseo in _VOSEO_FORMS:
            assert voseo not in result, (
                f"Found voseo form '{voseo}' in template_summary"
            )

    def test_mentions_llm_budget(self) -> None:
        cluster = make_cluster()
        result = template_summary(cluster)
        assert "presupuesto" in result.lower() or "agotado" in result.lower()
        assert "resumen" in result.lower()

    def test_spanish_content(self) -> None:
        cluster = make_cluster()
        result = template_summary(cluster)
        # Spanish diacritics preserved
        assert "presupuesto" in result or "presupuesto de LLM" in result

    def test_empty_cluster_handled(self) -> None:
        cluster = make_cluster(items=[])
        result = template_summary(cluster)
        # Should still produce a valid template string
        assert isinstance(result, str) and len(result) > 0


class TestStubSummary:
    """stub_summary in parser.py returns neutral Spanish LLMResponse."""

    def test_no_voseo_in_summary(self) -> None:
        cluster = make_cluster()
        result = stub_summary(cluster)
        for voseo in _VOSEO_FORMS:
            assert voseo not in result.summary, (
                f"Found voseo form '{voseo}' in stub_summary"
            )

    def test_mentions_no_llm(self) -> None:
        cluster = make_cluster()
        result = stub_summary(cluster)
        assert "sin llm" in result.summary.lower() or "sin LLM" in result.summary

    def test_spanish_summary(self) -> None:
        cluster = make_cluster()
        result = stub_summary(cluster)
        assert isinstance(result.summary, str)
        assert "no disponible" in result.summary

    def test_empty_highlights(self) -> None:
        cluster = make_cluster()
        result = stub_summary(cluster)
        assert result.highlights == []

    def test_cluster_id_matches_event_label(self) -> None:
        cluster = make_cluster(event_label="Specific Event")
        result = stub_summary(cluster)
        assert result.cluster_id == "Specific Event"
