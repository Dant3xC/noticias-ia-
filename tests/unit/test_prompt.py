"""Unit tests for the LLM prompt builder (llm/prompt.py).

Covers:
- build_prompt returns a 2-message list (system + user)
- The user message contains event label, sources, common facts, divergences
- The system prompt mentions Spanish and the JSON output shape
- Empty facts/divergences produce "Ninguno"/"Ninguna" placeholders
"""

from __future__ import annotations

from noticias.llm.prompt import SYSTEM_PROMPT, USER_PROMPT_TEMPLATE, build_prompt
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


class TestBuildPrompt:
    def test_returns_two_messages(self) -> None:
        payload = _make_payload()
        messages = build_prompt(payload)
        assert len(messages) == 2
        assert messages[0]["role"] == "system"
        assert messages[1]["role"] == "user"

    def test_system_prompt_mentions_spanish(self) -> None:
        assert "español" in SYSTEM_PROMPT
        assert "JSON" in SYSTEM_PROMPT

    def test_system_prompt_mentions_json_shape(self) -> None:
        assert "cluster_id" in SYSTEM_PROMPT
        assert "summary" in SYSTEM_PROMPT
        assert "highlights" in SYSTEM_PROMPT

    def test_user_contains_event_label(self) -> None:
        payload = _make_payload(event_label="Corte Suprema falla")
        messages = build_prompt(payload)
        user_content = messages[1]["content"]
        assert "Corte Suprema falla" in user_content

    def test_user_contains_sources(self) -> None:
        payload = _make_payload(
            sources=[("pagina12", "left"), ("infobae", "center")],
        )
        messages = build_prompt(payload)
        user_content = messages[1]["content"]
        assert "pagina12" in user_content
        assert "infobae" in user_content
        assert "left" in user_content
        assert "center" in user_content

    def test_user_contains_common_facts(self) -> None:
        payload = _make_payload(common_facts=["gobierno", "medidas"])
        messages = build_prompt(payload)
        user_content = messages[1]["content"]
        assert "gobierno" in user_content
        assert "medidas" in user_content

    def test_user_contains_divergences(self) -> None:
        payload = _make_payload(divergences=["presupuesto", "deuda"])
        messages = build_prompt(payload)
        user_content = messages[1]["content"]
        assert "presupuesto" in user_content
        assert "deuda" in user_content

    def test_empty_common_facts_placeholder(self) -> None:
        payload = _make_payload(common_facts=[])
        messages = build_prompt(payload)
        assert "Ninguno" in messages[1]["content"]

    def test_empty_divergences_placeholder(self) -> None:
        payload = _make_payload(divergences=[])
        messages = build_prompt(payload)
        assert "Ninguna" in messages[1]["content"]

    def test_template_constants(self) -> None:
        assert "{event_label}" in USER_PROMPT_TEMPLATE
        assert "{sources}" in USER_PROMPT_TEMPLATE
        assert "{common_facts}" in USER_PROMPT_TEMPLATE
        assert "{divergences}" in USER_PROMPT_TEMPLATE
