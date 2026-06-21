"""Unit tests for the Jaccard tokenizer (pipeline/tokenize.py).

Covers all Q2 rules from the design:
- Lowercase
- Accents preserved
- Stopwords removed
- Min-length filter (3 chars)
- Punctuation stripped
- NFKC normalization

Plus edge cases: empty string, stopword-only, punctuation-only.
"""

from __future__ import annotations

from noticias.pipeline.tokenize import STOPWORDS, tokenize


class TestTokenize:
    def test_lowercase(self) -> None:
        result = tokenize("HOLA MUNDO")
        assert "hola" in result
        assert "mundo" in result
        assert "HOLA" not in result

    def test_accents_preserved(self) -> None:
        """Accents are preserved: 'año' != 'ano'."""
        result = tokenize("El año pasado habló el presidente")
        assert "año" in result
        assert "habló" in result
        assert "presidente" in result
        # 'el' is a stopword, should be filtered
        assert "el" not in result

    def test_stopwords_removed(self) -> None:
        """All stopwords are filtered from the result."""
        text = "el la de en y un una con por para"
        result = tokenize(text)
        assert result == set()

    def test_min_length_filter(self) -> None:
        """Tokens shorter than 3 characters are removed."""
        result = tokenize("a an the ok no sí")
        assert all(len(t) >= 3 for t in result)
        # 'the' is not in Spanish stopwords, length 3 → kept
        assert "the" in result

    def test_punctuation_stripped(self) -> None:
        """Punctuation is replaced with spaces, only word chars survive."""
        result = tokenize("¡Hola, mundo! ¿Cómo estás?")
        assert "hola" in result
        assert "mundo" in result
        assert "cómo" in result
        assert "estás" in result

    def test_nfkc_normalization(self) -> None:
        """NFKC decomposes fullwidth chars and composes decomposed accents."""
        # Fullwidth letters (U+FF28 U+FF2F U+FF2C U+FF21 → "HOLA")
        result = tokenize("\uff28\uff2f\uff2c\uff21")
        assert "hola" in result

    def test_empty_string(self) -> None:
        assert tokenize("") == set()

    def test_only_stopwords(self) -> None:
        assert tokenize("el la de en y") == set()

    def test_only_punctuation(self) -> None:
        assert tokenize("¡¿...,!?;:-") == set()

    def test_mixed_case_and_stopwords(self) -> None:
        """Realistic: mixture of content words and stopwords."""
        result = tokenize("El presidente de la nación habló ayer sobre economía")
        assert "presidente" in result
        assert "nación" in result
        assert "habló" in result
        assert "ayer" in result
        assert "economía" in result
        # Stopwords removed
        assert "el" not in result
        assert "de" not in result
        assert "la" not in result

    def test_spanish_stopwords_list_length(self) -> None:
        """The stopword list should have approximately 40 entries (design Q2)."""
        assert len(STOPWORDS) >= 30, "Expected ~40 stopwords, got fewer"

    def test_duplicate_tokens_deduplicated(self) -> None:
        """Result is a set — no duplicates."""
        result = tokenize("casa casa casa")
        assert result == {"casa"}
