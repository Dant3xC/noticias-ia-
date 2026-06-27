"""Unit tests for the Embedder class (pipeline/embed.py).

All tests mock ``fastembed.TextEmbedding`` to avoid downloading the
~130 MB model or making network calls.

Covers:
- Empty list returns empty array
- Single text returns 1×D array
- Multiple texts return N×D array
- cosine_similarity correctness (identical, orthogonal, opposite, zero)
- is_similar boundary checks (at threshold, below threshold, custom threshold)
- Graceful failure: embed() returns None on exception
- Lazy loading: model not loaded until first embed() call
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from noticias.pipeline.embed import COSINE_THRESHOLD, Embedder


class TestEmbedder:
    """Tests for the Embedder class."""

    # ------------------------------------------------------------------
    # Embedding shape / dimensions
    # ------------------------------------------------------------------

    def test_empty_list_returns_empty_array(self) -> None:
        """embed([]) returns an empty (0, 0) array."""
        embedder = Embedder()
        result = embedder.embed([])
        assert isinstance(result, np.ndarray)
        assert result.shape == (0, 0)

    def test_single_text_returns_1xd_array(self) -> None:
        """embed(["text"]) returns shape (1, D) with mocked model."""
        # fastembed yields one 1-D vector per text.
        fake_vec = np.array([0.1, 0.2, 0.3])  # shape (D,)
        expected = np.array([[0.1, 0.2, 0.3]])  # shape (1, D)
        with patch(
            "noticias.pipeline.embed.TextEmbedding",
            return_value=_mock_model([fake_vec]),
        ):
            embedder = Embedder()
            result = embedder.embed(["some text"])
            np.testing.assert_array_almost_equal(result, expected)

    def test_multiple_texts_return_nxd_array(self) -> None:
        """embed(["a", "b", "c"]) returns shape (3, D)."""
        # fastembed yields one 1-D vector per text, so we pass three 1-D arrays.
        vecs = [np.array([0.1, 0.2]), np.array([0.3, 0.4]), np.array([0.5, 0.6])]
        expected = np.array([[0.1, 0.2], [0.3, 0.4], [0.5, 0.6]])
        with patch(
            "noticias.pipeline.embed.TextEmbedding",
            return_value=_mock_model(vecs),
        ):
            embedder = Embedder()
            result = embedder.embed(["a", "b", "c"])
            assert result.shape == (3, 2)
            np.testing.assert_array_almost_equal(result, expected)

    # ------------------------------------------------------------------
    # cosine_similarity
    # ------------------------------------------------------------------

    def test_cosine_identical_vectors(self) -> None:
        """Vectors pointing the same direction have cosine = 1.0."""
        a = np.array([1.0, 2.0, 3.0])
        assert Embedder.cosine_similarity(a, a) == pytest.approx(1.0)

    def test_cosine_orthogonal_vectors(self) -> None:
        """Orthogonal vectors have cosine = 0.0."""
        a = np.array([1.0, 0.0])
        b = np.array([0.0, 1.0])
        assert Embedder.cosine_similarity(a, b) == pytest.approx(0.0)

    def test_cosine_opposite_vectors(self) -> None:
        """Opposite vectors have cosine = -1.0."""
        a = np.array([1.0, 2.0])
        b = np.array([-1.0, -2.0])
        assert Embedder.cosine_similarity(a, b) == pytest.approx(-1.0)

    def test_cosine_zero_vector(self) -> None:
        """Zero vector returns 0.0 (no division by zero)."""
        a = np.array([1.0, 0.0])
        zero = np.array([0.0, 0.0])
        assert Embedder.cosine_similarity(a, zero) == 0.0
        assert Embedder.cosine_similarity(zero, a) == 0.0
        assert Embedder.cosine_similarity(zero, zero) == 0.0

    # ------------------------------------------------------------------
    # is_similar
    # ------------------------------------------------------------------

    def test_is_similar_at_threshold(self) -> None:
        """is_similar returns True when cosine == COSINE_THRESHOLD."""
        # Two vectors at exactly 0.85 cosine.
        a = np.array([1.0, 0.0])
        # cos(a, b) = 1*0.85 + 0*√(1-0.85²) = 0.85
        theta = np.arccos(COSINE_THRESHOLD)
        b = np.array([np.cos(theta), np.sin(theta)])
        assert Embedder.is_similar(a, b) is True

    def test_is_similar_below_threshold(self) -> None:
        """is_similar returns False when cosine < COSINE_THRESHOLD."""
        a = np.array([1.0, 0.0])
        # cos(a, b) = cos(60°) ≈ 0.5 < 0.85
        theta = np.radians(60.0)
        b = np.array([np.cos(theta), np.sin(theta)])
        assert Embedder.is_similar(a, b) is False

    def test_is_similar_custom_threshold(self) -> None:
        """is_similar works with a custom threshold."""
        a = np.array([1.0, 0.0])
        b = np.array([0.0, 1.0])  # cosine = 0.0
        # With a threshold of -0.5, these should be considered similar.
        assert Embedder.is_similar(a, b, threshold=-0.5) is True
        # With a higher threshold, they shouldn't.
        assert Embedder.is_similar(a, b, threshold=0.5) is False

    # ------------------------------------------------------------------
    # Graceful failure
    # ------------------------------------------------------------------

    def test_embed_returns_none_on_exception(self) -> None:
        """When fastembed raises, embed() returns None (graceful degr.)."""
        with patch(
            "noticias.pipeline.embed.TextEmbedding",
            side_effect=RuntimeError("Model download failed"),
        ):
            embedder = Embedder()
            result = embedder.embed(["some text"])
            assert result is None

    def test_embed_returns_none_on_model_exception(self) -> None:
        """When the model's embed() method raises, embed() returns None."""
        mock_model = MagicMock()
        mock_model.embed.side_effect = ValueError("Corrupt model file")
        with patch(
            "noticias.pipeline.embed.TextEmbedding",
            return_value=mock_model,
        ):
            embedder = Embedder()
            result = embedder.embed(["some text"])
            assert result is None

    # ------------------------------------------------------------------
    # Lazy loading
    # ------------------------------------------------------------------

    def test_model_not_loaded_at_init(self) -> None:
        """Embedder() does NOT load the model — lazy."""
        with patch("noticias.pipeline.embed.TextEmbedding") as mock_cls:
            embedder = Embedder()
            mock_cls.assert_not_called()
            # After calling embed, it SHOULD load.
            mock_model = MagicMock()
            mock_model.embed.return_value = [np.array([0.1, 0.2])]
            mock_cls.return_value = mock_model
            embedder.embed(["hello"])
            mock_cls.assert_called_once()

    def test_model_loaded_only_once(self) -> None:
        """Multiple embed() calls reuse the same model instance."""
        with patch("noticias.pipeline.embed.TextEmbedding") as mock_cls:
            mock_model = MagicMock()
            mock_model.embed.return_value = [np.array([0.1, 0.2])]
            mock_cls.return_value = mock_model

            embedder = Embedder()
            embedder.embed(["first"])
            embedder.embed(["second"])
            # TextEmbedding constructor called exactly once.
            mock_cls.assert_called_once()

    # ------------------------------------------------------------------
    # COSINE_THRESHOLD constant
    # ------------------------------------------------------------------

    def test_cosine_threshold_constant(self) -> None:
        """COSINE_THRESHOLD is 0.85 as specified in design."""
        assert COSINE_THRESHOLD == 0.85


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def _mock_model(return_values: list[np.ndarray]) -> MagicMock:
    """Build a mock fastembed TextEmbedding model.

    Args:
        return_values: A list of 1-D arrays (one per embed call).

    Returns:
        A MagicMock whose ``embed()`` yields the given vectors.
    """
    model = MagicMock()
    model.embed.return_value = return_values
    return model
