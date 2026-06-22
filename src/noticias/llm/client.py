"""LLM client wrapping LiteLLM with fallback chain and token budget.

The client loads API keys from environment variables (``GROQ_API_KEY``,
``GEMINI_API_KEY``, ``OPENAI_API_KEY``) and stores them in a private
``_keys`` dict that is NEVER logged or exposed via ``__repr__``.

Provider fallback order:
    1. ``groq/llama-3.1-8b-instant``
    2. ``gemini/gemini-2.0-flash-exp``
    3. ``gpt-4o-mini``
"""

from __future__ import annotations

import logging
import os
from typing import Any

import litellm

from noticias.models.cluster import Cluster

logger = logging.getLogger(__name__)


class TokenBudgetExceeded(Exception):
    """Raised when an LLM call would exceed the remaining token budget.

    The orchestrator may catch this and assign a template summary to the
    affected cluster.
    """


class LLMClient:
    """LiteLLM wrapper with provider fallback, token budget tracking, and
    safe API key handling.

    API keys are read from environment variables and stored in a private
    ``_keys`` attribute. The ``__repr__`` masks all keys.
    """

    DEFAULT_MODELS: list[str] = [
        "groq/llama-3.1-8b-instant",
        "gemini/gemini-2.0-flash-exp",
        "gpt-4o-mini",
    ]

    def __init__(
        self,
        models: list[str] | None = None,
        token_budget: int = 5000,
    ) -> None:
        """Initialise the LLM client.

        Args:
            models: Ordered list of LiteLLM model strings. Defaults to
                ``DEFAULT_MODELS``.
            token_budget: Maximum cumulative tokens per run (default 5000).

        Raises:
            ValueError: If ``token_budget`` is negative.
        """
        if token_budget < 0:
            raise ValueError(f"token_budget must be non-negative, got {token_budget}")

        self.models = models or list(self.DEFAULT_MODELS)
        self.token_budget: int = token_budget
        self.tokens_used: int = 0

        # API keys stored PRIVATE — never logged or exposed.
        self._keys: dict[str, str | None] = {
            "groq": os.environ.get("GROQ_API_KEY"),
            "gemini": os.environ.get("GEMINI_API_KEY"),
            "openai": os.environ.get("OPENAI_API_KEY"),
        }

    async def complete(
        self,
        messages: list[dict[str, str]],
        json_mode: bool = True,
    ) -> str | None:
        """Send messages to the LLM with fallback across providers.

        Tries each model in order. For each model, checks whether the
        provider's API key is set. If the key is missing, the model is
        skipped. On any exception, a warning is logged and the next
        model is tried.

        Args:
            messages: A list of message dicts (typically system + user)
                as required by the LiteLLM / OpenAI chat API.
            json_mode: If ``True``, requests JSON-structured output via
                ``response_format={"type": "json_object"}``.

        Returns:
            The raw response content string on success, or ``None`` if
            all providers failed.

        Raises:
            TokenBudgetExceeded: If the estimated tokens for the last
                message content would exceed the remaining budget.
        """
        # Budget safety check.
        last_content = messages[-1]["content"] if messages else ""
        estimated = self.estimate_tokens(last_content)
        if self.tokens_used + estimated > self.token_budget:
            raise TokenBudgetExceeded(
                f"Token budget {self.token_budget} would be exceeded "
                f"({self.tokens_used} used + {estimated} estimated)",
            )

        for model in self.models:
            provider = model.split("/")[0].lower()
            if not self._keys.get(provider):
                logger.debug("Skipping %s: no API key configured", model)
                continue

            try:
                kwargs: dict[str, Any] = {
                    "model": model,
                    "messages": messages,
                }
                if json_mode:
                    kwargs["response_format"] = {"type": "json_object"}

                response = await litellm.acompletion(**kwargs)  # type: ignore[no-untyped-call]
                content: str | None = response.choices[0].message.content

                if content is None:
                    logger.warning("Empty response from %s", model)
                    continue

                self.tokens_used += estimated
                return content

            except Exception as exc:
                logger.warning(
                    "provider %s failed: %s",
                    model,
                    type(exc).__name__,
                )
                continue

        logger.warning("All LLM providers failed for this request")
        return None

    @staticmethod
    def estimate_tokens(text: str) -> int:
        """Rough token estimate using char/4 rule.

        Args:
            text: The input text to estimate.

        Returns:
            Estimated token count (``len(text) // 4``).
        """
        return len(text) // 4

    @property
    def budget_remaining(self) -> int:
        """Tokens remaining before hitting the budget cap."""
        return self.token_budget - self.tokens_used

    def __repr__(self) -> str:
        """Return a repr that does NOT leak API keys.

        Provider parts are shown (e.g. ``groq/...``) but the model
        suffix and all key values are masked.
        """
        models_repr = [f"{m.split('/')[0]}/..." for m in self.models]
        return (
            f"LLMClient(models={models_repr!r}, "
            f"token_budget={self.token_budget})"
        )


def template_summary(cluster: Cluster) -> str:
    """Generate a Spanish template summary string.

    Used when the LLM budget is exhausted or no API keys are configured.

    Args:
        cluster: The cluster (used for its event_label).

    Returns:
        A neutral Spanish template string (no voseo).
    """
    return (
        "Sin resumen disponible "
        "(presupuesto de LLM agotado o sin claves configuradas)."
    )


class StubLLMClient:
    """LLM client that always returns stub summaries (for ``--no-llm`` mode).

    Does **not** load API keys, does **not** make network calls.
    ``estimate_tokens`` returns 0 and ``budget_remaining`` returns 0
    so that the orchestrator's budget check passes without consuming
    the budget.
    """

    def __init__(self) -> None:
        self.tokens_used: int = 0
        self.token_budget: int = 0

    async def complete(
        self,
        messages: list[dict[str, str]],
        json_mode: bool = True,  # noqa: ARG002
    ) -> str | None:
        """Return a stub JSON summary immediately (no network call)."""
        return (
            '{"summary": "Resumen no disponible (modo --no-llm).", '
            '"highlights": []}'
        )

    @staticmethod
    def estimate_tokens(text: str) -> int:  # noqa: ARG004
        """Return 0 — no tokens consumed in stub mode."""
        return 0

    @property
    def budget_remaining(self) -> int:
        """Always 0 — stub client does not consume budget."""
        return 0

    def __repr__(self) -> str:
        return "StubLLMClient()"
