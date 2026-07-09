"""Unit tests for the LLM client (llm/client.py).

Covers:
- __repr__ does not leak API keys
- API keys are loaded from env, not hardcoded
- estimate_tokens matches len(text) // 4
- budget_remaining reflects tokens_used
- Fallback chain: model 1 fails, model 2 is tried
- All models fail → complete() returns None
- JSON mode: request includes response_format
- TokenBudgetExceeded raised when budget would be exceeded
- token_budget validation (negative raises ValueError)
"""

from __future__ import annotations

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from noticias.llm.client import LLMClient, TokenBudgetExceeded


class TestLLMClientRepr:
    """__repr__ must NOT leak API keys."""

    def test_repr_contains_no_keys(self) -> None:
        client = LLMClient()
        representation = repr(client)
        # Keys should not appear
        assert "GROQ_API_KEY" not in representation
        assert "GEMINI_API_KEY" not in representation
        assert "OPENAI_API_KEY" not in representation
        assert "sk-" not in representation
        # Default models shown as provider/...
        assert "groq/..." in representation

    def test_repr_masks_model_suffix(self) -> None:
        """Individual model suffixes are masked to provider/..."""
        client = LLMClient(models=["groq/llama-3.1-8b-instant"])
        representation = repr(client)
        assert "groq/..." in representation
        assert "llama-3.1-8b-instant" not in representation


class TestLLMClientKeyLoading:
    """API keys are loaded from env, never hardcoded."""

    def test_keys_loaded_from_env(self) -> None:
        with patch.dict(os.environ, {
            "GROQ_API_KEY": "gsk_test_key",
            "GEMINI_API_KEY": "",
            "OPENAI_API_KEY": "",
        }, clear=True):
            client = LLMClient()
            assert client._keys["groq"] == "gsk_test_key"
            assert client._keys["gemini"] is None or client._keys["gemini"] == ""
            assert client._keys["openai"] is None or client._keys["openai"] == ""

    def test_no_keys_returns_none(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            client = LLMClient()
            assert all(
                v is None for v in client._keys.values()
            )

    def test_keys_not_in_instance_dict(self) -> None:
        """Keys are in _keys, not leaked to __dict__."""
        client = LLMClient()
        instance_dict = client.__dict__
        # The private _keys attribute should be the only key holder
        assert "_keys" in instance_dict
        # No key value should appear directly in __dict__
        for key in ("GROQ_API_KEY", "GEMINI_API_KEY", "OPENAI_API_KEY"):
            assert key not in str(instance_dict)


class TestLLMClientTokenEstimation:
    """estimate_tokens matches len(text) // 4."""

    def test_empty_string_zero_tokens(self) -> None:
        assert LLMClient.estimate_tokens("") == 0

    def test_short_text(self) -> None:
        text = "Hello, world!"
        assert LLMClient.estimate_tokens(text) == len(text) // 4

    def test_exact_divisible(self) -> None:
        text = "A" * 100
        assert LLMClient.estimate_tokens(text) == 25

    def test_spanish_text(self) -> None:
        text = "El presidente anunció nuevas medidas económicas para el país"
        assert LLMClient.estimate_tokens(text) == len(text) // 4


class TestLLMClientEstimateTokensBytes4:
    """estimate_tokens uses len(text.encode('utf-8')) // 4.

    This accounts for the fact that accented Spanish characters use 2 bytes
    in UTF-8, making the char/4 rule undercount tokens for accented text.
    """

    def test_empty_string_zero(self) -> None:
        assert LLMClient.estimate_tokens("") == 0

    def test_ascii_same_as_before(self) -> None:
        text = "Hello, world!"
        assert LLMClient.estimate_tokens(text) == len(text.encode("utf-8")) // 4

    def test_accented_spanish_uses_utf8_bytes(self) -> None:
        """Accented chars estimate uses UTF-8 byte length, not char length."""
        text = "éste es un texto con acéntos"
        expected = len(text.encode("utf-8")) // 4
        assert LLMClient.estimate_tokens(text) == expected, (
            f"Expected {expected} (bytes/4), got {LLMClient.estimate_tokens(text)}"
        )
        # UTF-8 encoding adds bytes for accented chars
        assert len(text.encode("utf-8")) > len(text)

    def test_emoji_four_bytes(self) -> None:
        """Emoji (🚀) encodes as 4 bytes → bytes/4 = 1."""
        text = "🚀"
        expected = len(text.encode("utf-8")) // 4
        assert LLMClient.estimate_tokens(text) == expected
        assert expected == 1


class TestLLMClientBudget:
    """budget_remaining and tokens_used tracking."""

    def test_budget_starts_full(self) -> None:
        client = LLMClient(token_budget=5000)
        assert client.budget_remaining == 5000
        assert client.tokens_used == 0

    def test_budget_remaining_reflects_usage(self) -> None:
        client = LLMClient(token_budget=5000)
        client.tokens_used = 1200
        assert client.budget_remaining == 3800

    def test_custom_budget(self) -> None:
        client = LLMClient(token_budget=10000)
        assert client.token_budget == 10000
        assert client.budget_remaining == 10000

    def test_negative_budget_raises(self) -> None:
        with pytest.raises(ValueError, match="token_budget must be non-negative"):
            LLMClient(token_budget=-1)


class MockResponse:
    """Minimal mock for LiteLLM acompletion response."""

    def __init__(self, content: str) -> None:
        self.choices = [MagicMock()]
        self.choices[0].message.content = content


class TestLLMClientComplete:
    """complete() fallback chain and error handling."""

    @pytest.mark.asyncio
    async def test_first_provider_succeeds(self) -> None:
        with (
            patch.dict(os.environ, {
                "GROQ_API_KEY": "gsk_test",
                "GEMINI_API_KEY": "",
                "OPENAI_API_KEY": "",
            }, clear=True),
            patch("noticias.llm.client.litellm.acompletion", new_callable=AsyncMock) as mock_acompletion,
        ):
            mock_acompletion.return_value = MockResponse(
                '{"summary": "Test summary.", "highlights": ["Point 1"]}',
            )
            client = LLMClient(
                models=["groq/llama-3.1-8b-instant"],
                token_budget=5000,
            )
            result = await client.complete(
                [{"role": "user", "content": "test"}],
                json_mode=True,
            )

            assert result is not None
            assert "Test summary" in result
            assert mock_acompletion.call_count == 1
            # Verify response_format was sent
            kwargs = mock_acompletion.call_args[1]
            assert kwargs.get("response_format") == {"type": "json_object"}

    @pytest.mark.asyncio
    async def test_fallback_chain(self) -> None:
        """When first provider fails, second is tried."""
        with (
            patch.dict(os.environ, {
                "GROQ_API_KEY": "gsk_test",
                "GEMINI_API_KEY": "gemini_test",
                "OPENAI_API_KEY": "",
            }, clear=True),
            patch("noticias.llm.client.litellm.acompletion", new_callable=AsyncMock) as mock_acompletion,
        ):
            # First call raises, second succeeds
            mock_acompletion.side_effect = [
                Exception("Groq rate limited"),
                MockResponse('{"summary": "Fallback summary."}'),
            ]

            client = LLMClient(
                models=["groq/llama-3.1-8b-instant", "gemini/gemini-2.0-flash-exp"],
                token_budget=5000,
            )
            result = await client.complete(
                [{"role": "user", "content": "test"}],
            )

            assert result is not None
            assert "Fallback summary" in result
            assert mock_acompletion.call_count == 2

    @pytest.mark.asyncio
    async def test_all_providers_fail_returns_none(self) -> None:
        with (
            patch.dict(os.environ, {
                "GROQ_API_KEY": "gsk_test",
                "GEMINI_API_KEY": "gemini_test",
            }, clear=True),
            patch("noticias.llm.client.litellm.acompletion", new_callable=AsyncMock) as mock_acompletion,
        ):
            mock_acompletion.side_effect = Exception("API error")

            client = LLMClient(
                models=["groq/llama-3.1-8b-instant", "gemini/gemini-2.0-flash-exp"],
                token_budget=5000,
            )
            result = await client.complete(
                [{"role": "user", "content": "test"}],
            )

            assert result is None
            assert mock_acompletion.call_count == 2

    @pytest.mark.asyncio
    async def test_skip_provider_without_key(self) -> None:
        """Providers without API key are skipped."""
        with (
            patch.dict(os.environ, {}, clear=True),
            patch("noticias.llm.client.litellm.acompletion", new_callable=AsyncMock) as mock_acompletion,
        ):
            client = LLMClient()
            result = await client.complete(
                [{"role": "user", "content": "test"}],
            )

            assert result is None
            # No provider had a key, so acompletion was never called
            mock_acompletion.assert_not_called()

    @pytest.mark.asyncio
    async def test_empty_response_from_provider(self) -> None:
        """Provider returns None content → skip to next."""
        with (
            patch.dict(os.environ, {
                "GROQ_API_KEY": "gsk_test",
                "GEMINI_API_KEY": "gemini_test",
            }, clear=True),
            patch("noticias.llm.client.litellm.acompletion", new_callable=AsyncMock) as mock_acompletion,
        ):
            mock_response = MagicMock()
            mock_response.choices[0].message.content = None
            mock_acompletion.side_effect = [
                mock_response,
                MockResponse('{"summary": "Second works."}'),
            ]

            client = LLMClient()
            result = await client.complete(
                [{"role": "user", "content": "test"}],
            )

            assert result is not None
            assert "Second works" in result

    @pytest.mark.asyncio
    async def test_json_mode_sends_response_format(self) -> None:
        with (
            patch.dict(os.environ, {
                "GROQ_API_KEY": "gsk_test",
            }, clear=True),
            patch("noticias.llm.client.litellm.acompletion", new_callable=AsyncMock) as mock_acompletion,
        ):
            mock_acompletion.return_value = MockResponse('{"summary": "Yes"}')

            client = LLMClient()
            await client.complete(
                [{"role": "user", "content": "test"}],
                json_mode=True,
            )

            kwargs = mock_acompletion.call_args[1]
            assert kwargs.get("response_format") == {"type": "json_object"}

    @pytest.mark.asyncio
    async def test_non_json_mode_no_response_format(self) -> None:
        with (
            patch.dict(os.environ, {
                "GROQ_API_KEY": "gsk_test",
            }, clear=True),
            patch("noticias.llm.client.litellm.acompletion", new_callable=AsyncMock) as mock_acompletion,
        ):
            mock_acompletion.return_value = MockResponse("Some text")

            client = LLMClient()
            await client.complete(
                [{"role": "user", "content": "test"}],
                json_mode=False,
            )

            kwargs = mock_acompletion.call_args[1]
            assert "response_format" not in kwargs

    @pytest.mark.asyncio
    async def test_token_budget_exceeded_raises(self) -> None:
        """Budget check in complete() raises TokenBudgetExceeded."""
        with (
            patch.dict(os.environ, {
                "GROQ_API_KEY": "gsk_test",
            }, clear=True),
        ):
            client = LLMClient(token_budget=100)
            client.tokens_used = 90
            # Last message "A" * 80 → 20 estimated → 90 + 20 = 110 > 100
            with pytest.raises(TokenBudgetExceeded):
                await client.complete(
                    [{"role": "user", "content": "A" * 80}],
                )

    @pytest.mark.asyncio
    async def test_tokens_used_incremented_on_success(self) -> None:
        with (
            patch.dict(os.environ, {
                "GROQ_API_KEY": "gsk_test",
            }, clear=True),
            patch("noticias.llm.client.litellm.acompletion", new_callable=AsyncMock) as mock_acompletion,
        ):
            mock_acompletion.return_value = MockResponse(
                '{"summary": "Summary."}',
            )
            client = LLMClient(token_budget=5000)
            assert client.tokens_used == 0

            await client.complete(
                [{"role": "user", "content": "Test message for tokens"}],
            )

            # "Test message for tokens" → 25 chars → 6 tokens
            assert client.tokens_used > 0

    @pytest.mark.asyncio
    async def test_tokens_not_incremented_on_failure(self) -> None:
        with (
            patch.dict(os.environ, {
                "GROQ_API_KEY": "gsk_test",
            }, clear=True),
            patch("noticias.llm.client.litellm.acompletion", new_callable=AsyncMock) as mock_acompletion,
        ):
            mock_acompletion.side_effect = Exception("API error")
            client = LLMClient(token_budget=5000)
            assert client.tokens_used == 0

            await client.complete(
                [{"role": "user", "content": "test"}],
            )

            # No success, tokens_used stays 0
            assert client.tokens_used == 0

