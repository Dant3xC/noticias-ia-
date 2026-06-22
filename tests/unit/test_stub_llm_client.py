"""Unit tests for StubLLMClient — LLMClient subclass for --no-llm mode.

Verifies:
- StubLLMClient is an instance of LLMClient (type safety fix)
- complete() returns valid JSON string
- estimate_tokens returns 0
- budget_remaining returns 0
- __init__ does NOT load env keys
"""

from __future__ import annotations

import json
import os
from unittest.mock import patch

import pytest

from noticias.llm.client import LLMClient, StubLLMClient


class TestStubLLMClientIsSubclass:
    """StubLLMClient must be a proper subclass of LLMClient."""

    def test_is_instance_of_llm_client(self) -> None:
        client = StubLLMClient()
        assert isinstance(client, LLMClient)

    def test_is_subclass(self) -> None:
        assert issubclass(StubLLMClient, LLMClient)


class TestStubLLMClientInit:
    """__init__ must NOT load env keys."""

    def test_no_env_keys_loaded(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            client = StubLLMClient()
            assert client._keys == {}
            assert client.token_budget == 0
            assert client.tokens_used == 0
            assert client.models == []

    def test_still_empty_even_with_env_keys_present(self) -> None:
        """StubLLMClient intentionally skips env loading."""
        with patch.dict(os.environ, {
            "GROQ_API_KEY": "gsk_test",
            "GEMINI_API_KEY": "gemini_test",
            "OPENAI_API_KEY": "sk-test",
        }, clear=True):
            client = StubLLMClient()
            assert client._keys == {}
            assert client.token_budget == 0


class TestStubLLMClientComplete:
    """complete() returns a valid JSON string immediately."""

    @pytest.mark.asyncio
    async def test_returns_valid_json(self) -> None:
        client = StubLLMClient()
        result = await client.complete(
            [{"role": "user", "content": "test"}],
        )
        assert result is not None
        parsed = json.loads(result)
        assert "summary" in parsed
        assert "highlights" in parsed
        assert isinstance(parsed["highlights"], list)
        assert "Resumen no disponible" in parsed["summary"]

    @pytest.mark.asyncio
    async def test_accepts_json_mode_flag(self) -> None:
        """Should accept and ignore json_mode (no-op in stub)."""
        client = StubLLMClient()
        result = await client.complete(
            [{"role": "user", "content": "test"}],
            json_mode=True,
        )
        assert result is not None
        assert json.loads(result) is not None

    @pytest.mark.asyncio
    async def test_needs_no_api_key(self) -> None:
        """Complete works with empty env (no key loading needed)."""
        with patch.dict(os.environ, {}, clear=True):
            client = StubLLMClient()
            result = await client.complete(
                [{"role": "user", "content": "test"}],
            )
            assert result is not None


class TestStubLLMClientTokenEstimation:
    """estimate_tokens always returns 0."""

    def test_empty_string(self) -> None:
        assert StubLLMClient.estimate_tokens("") == 0

    def test_long_text(self) -> None:
        assert StubLLMClient.estimate_tokens("A" * 10000) == 0

    def test_spanish_text(self) -> None:
        assert StubLLMClient.estimate_tokens(
            "El presidente anunció nuevas medidas económicas para el país",
        ) == 0


class TestStubLLMClientBudget:
    """budget_remaining always returns 0."""

    def test_budget_starts_at_zero(self) -> None:
        client = StubLLMClient()
        assert client.budget_remaining == 0

    def test_budget_never_changes(self) -> None:
        client = StubLLMClient()
        client.tokens_used = 9999  # manually set — shouldn't affect budget
        assert client.budget_remaining == 0


class TestStubLLMClientRepr:
    """__repr__ returns a fixed string with no keys."""

    def test_repr_no_keys(self) -> None:
        client = StubLLMClient()
        representation = repr(client)
        assert representation == "StubLLMClient()"
        assert "GROQ_API_KEY" not in representation
        assert "sk-" not in representation
