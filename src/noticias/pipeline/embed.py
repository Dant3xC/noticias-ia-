"""Embedder class for semantic clustering.

Wraps fastembed with lazy model loading, graceful failure handling,
and cosine similarity for use as a clustering similarity signal.
"""

from __future__ import annotations

import logging
from typing import Sequence

import numpy as np
from fastembed import TextEmbedding  # type: ignore[import-untyped]

logger = logging.getLogger(__name__)

# Default cosine similarity threshold for semantic clustering.
# Two titles are considered similar when their cosine similarity >= this value.
COSINE_THRESHOLD: float = 0.85


class Embedder:
    """Lazy wrapper around fastembed for text embeddings.

    The model is loaded on first call to embed(). On any error, embed()
    returns None and the caller falls back to rapidfuzz.

    Example::

        embedder = Embedder()
        vecs = embedder.embed(["Noticia de prueba"])
        if vecs is not None:
            sim = Embedder.cosine_similarity(vecs[0], vecs[1])
    """

    def __init__(self, model_name: str = "BAAI/bge-small-multilingual-v1") -> None:
        self._model_name = model_name
        self._model = None

    def _load(self) -> None:
        """Lazy-load the fastembed TextEmbedding model (called on first embed).

        The import of ``TextEmbedding`` happens at module load time — what is
        lazy here is the **model instantiation**, which downloads ~130 MB of
        weights on first use.
        """
        if self._model is None:
            self._model = TextEmbedding(model_name=self._model_name)

    def embed(self, texts: Sequence[str]) -> np.ndarray | None:
        """Return a (N, D) array of embeddings, or None on failure.

        Args:
            texts: A sequence of text strings to embed.

        Returns:
            A NumPy array of shape (N, D) where N=len(texts) and D is the
            embedding dimension, or None if the model could not be loaded or
            the embedding call raised an exception.
        """
        if not texts:
            return np.empty((0, 0))
        try:
            self._load()
            embeddings = list(self._model.embed(list(texts)))
            return np.array(embeddings)
        except Exception as e:
            logger.warning(
                "Embedder.embed failed: %s. Falling back to rapidfuzz.", e,
            )
            return None

    @staticmethod
    def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
        """Cosine similarity between two vectors.

        Args:
            a: A 1-D NumPy array.
            b: A 1-D NumPy array.

        Returns:
            The cosine similarity as a float in [-1.0, 1.0].
            Returns 0.0 if either vector has zero norm.
        """
        denom = np.linalg.norm(a) * np.linalg.norm(b)
        if denom == 0:
            return 0.0
        return float(np.dot(a, b) / denom)

    @staticmethod
    def is_similar(
        a: np.ndarray,
        b: np.ndarray,
        threshold: float = COSINE_THRESHOLD,
    ) -> bool:
        """True if cosine similarity between *a* and *b* is >= *threshold*.

        Args:
            a: A 1-D NumPy array.
            b: A 1-D NumPy array.
            threshold: Minimum cosine similarity to consider "similar".
                Defaults to ``COSINE_THRESHOLD`` (0.85).

        Returns:
            True when similarity >= threshold; False otherwise.
        """
        return Embedder.cosine_similarity(a, b) >= threshold
