"""Spanish prompt templates for LLM summary generation.

The system prompt instructs the LLM to write summaries in Spanish using
only facts from the family-format payload. The user prompt template
inserts the structured event data.
"""

from __future__ import annotations

from noticias.models.cluster import FamilyFormatPayload

# Language: neutral Spanish (no voseo).
SYSTEM_PROMPT = (
    "Eres un asistente que resume noticias de múltiples fuentes "
    "para un lector argentino. Reglas: "
    "1) Escribe SIEMPRE en español, 2-3 oraciones. "
    "2) Usa SOLO los hechos presentes en el payload. "
    "3) Si los hechos son insuficientes, indica "
    "'Información insuficiente'. "
    "4) Devuelve JSON con esta forma: "
    '{"cluster_id": "...", "summary": "...", '
    '"highlights": ["...", "..."]}.'
)

USER_PROMPT_TEMPLATE = (
    "Evento: {event_label}\n"
    "Fuentes: {sources}\n"
    "Hechos comunes: {common_facts}\n"
    "Divergencias: {divergences}\n\n"
    "Escribe el resumen y 2-3 viñetas de highlights."
)


def build_prompt(payload: FamilyFormatPayload) -> list[dict[str, str]]:
    """Build the message list for the LLM call.

    Constructs a system message with the instruction prompt and a user
    message with the event data from the payload.

    Args:
        payload: The compact per-cluster ``FamilyFormatPayload``.

    Returns:
        A list of two message dicts (``[system, user]``) ready for
        ``litellm.acompletion(messages=...)``.
    """
    sources_str = ", ".join(
        f"{s.name} ({s.lean})" for s in payload.sources
    )
    common_facts_str = (
        ", ".join(payload.common_facts) if payload.common_facts else "Ninguno"
    )
    divergences_str = (
        ", ".join(payload.divergences) if payload.divergences else "Ninguna"
    )

    user_content = USER_PROMPT_TEMPLATE.format(
        event_label=payload.event_label,
        sources=sources_str,
        common_facts=common_facts_str,
        divergences=divergences_str,
    )

    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]
