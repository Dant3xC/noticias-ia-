"""Unit tests for the LLM prompt builder (llm/prompt.py).

Covers:
- build_prompt returns a 2-message list (system + user)
- The user message contains event label, sources, common facts, divergences
- The system prompt mentions Spanish and the JSON output shape
- Empty facts/divergences produce "Ninguno"/"Ninguna" placeholders
"""

from __future__ import annotations

from noticias.llm.prompt import SYSTEM_PROMPT, build_batch_prompt
from noticias.models.cluster import FamilyFormatPayload


def _make_payload(
    event_label: str = "Test Event",
    sources: list[tuple[str, str]] | None = None,
    common_facts: list[str] | None = None,
    divergences: list[str] | None = None,
) -> FamilyFormatPayload:
    from noticias.models.cluster import FamilyFormatSource, PerSourceEntry

    if sources is None:
        sources = [("source_a", "left")]
    if common_facts is None:
        common_facts = ["fact1", "fact2"]
    if divergences is None:
        divergences = ["div1"]

    return FamilyFormatPayload(
        event_label=event_label,
        sources=[
            FamilyFormatSource(name=name, lean=lean)
            for name, lean in sources
        ],
        per_source=[
            PerSourceEntry(
                source=sources[0][0],
                headline="Headline",
                body_excerpt="Body...",
                published_at="2026-06-21T12:00:00+00:00",
            ),
        ],
        common_facts=common_facts,
        divergences=divergences,
    )


class TestBuildClusterBlock:
    """Tests for ``build_cluster_block`` — per-payload text block."""

    def test_returns_string(self) -> None:
        payload = _make_payload(event_label="Test Event")
        from noticias.llm.prompt import build_cluster_block

        block = build_cluster_block(payload)
        assert isinstance(block, str)
        assert len(block) > 0

    def test_contains_event_label(self) -> None:
        from noticias.llm.prompt import build_cluster_block

        payload = _make_payload(event_label="Caso especial")
        block = build_cluster_block(payload)
        assert "Caso especial" in block

    def test_contains_sources_with_lean(self) -> None:
        from noticias.llm.prompt import build_cluster_block

        payload = _make_payload(
            sources=[("pagina12", "left"), ("infobae", "center")],
        )
        block = build_cluster_block(payload)
        assert "pagina12" in block
        assert "infobae" in block
        assert "left" in block
        assert "center" in block

    def test_contains_common_facts(self) -> None:
        from noticias.llm.prompt import build_cluster_block

        payload = _make_payload(common_facts=["gobierno", "medidas"])
        block = build_cluster_block(payload)
        assert "gobierno" in block
        assert "medidas" in block

    def test_contains_divergences(self) -> None:
        from noticias.llm.prompt import build_cluster_block

        payload = _make_payload(divergences=["div_a", "div_b"])
        block = build_cluster_block(payload)
        assert "div_a" in block
        assert "div_b" in block

    def test_placeholder_when_no_facts(self) -> None:
        from noticias.llm.prompt import build_cluster_block

        payload = _make_payload(common_facts=[], divergences=[])
        block = build_cluster_block(payload)
        assert "Ninguno" in block or "Ninguna" in block


class TestBuildBatchPrompt:
    """Tests for ``build_batch_prompt`` — the multi-cluster mega-prompt."""

    def test_returns_two_messages(self) -> None:
        payloads = [_make_payload(event_label="A"), _make_payload(event_label="B")]
        messages = build_batch_prompt(payloads)
        assert len(messages) == 2
        assert messages[0]["role"] == "system"
        assert messages[1]["role"] == "user"

    def test_user_content_contains_all_clusters(self) -> None:
        payloads = [
            _make_payload(event_label="Cluster Alpha"),
            _make_payload(event_label="Cluster Beta"),
        ]
        messages = build_batch_prompt(payloads)
        user_content = messages[1]["content"]
        assert "Cluster Alpha" in user_content
        assert "Cluster Beta" in user_content
        assert "Aquí hay 2 clusters" in user_content

    def test_each_cluster_block_has_sources_facts_divergences(self) -> None:
        payloads = [
            _make_payload(
                event_label="Test",
                sources=[("src1", "left"), ("src2", "center")],
                common_facts=["fact_a"],
                divergences=["div_x"],
            ),
        ]
        messages = build_batch_prompt(payloads)
        user_content = messages[1]["content"]
        assert "sources" in user_content.lower() or "src1" in user_content
        assert "fact_a" in user_content
        assert "div_x" in user_content

    def test_system_prompt_mentions_batch_format(self) -> None:
        assert "clusters" in SYSTEM_PROMPT
        assert "cluster_id" in SYSTEM_PROMPT
        assert "summary" in SYSTEM_PROMPT

    def test_single_cluster_still_works(self) -> None:
        payloads = [_make_payload(event_label="Solo")]
        messages = build_batch_prompt(payloads)
        user_content = messages[1]["content"]
        assert "Aquí hay 1 cluster" in user_content
        assert "Solo" in user_content
