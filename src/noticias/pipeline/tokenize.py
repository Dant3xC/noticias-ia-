"""
Jaccard tokenizer for Spanish text used in story clustering, dedup, and
family-format common-facts / divergences computation.

Rules (design Q2):
- Unicode NFKC normalization (composes decomposed chars, handles fullwidth forms)
- Lowercase
- Punctuation stripped (keep only \\w and \\s — retains accented letters)
- Min token length 3 (filters articles, prepositions, conjunctions)
- Stopword removal (inline Spanish list, ~40 words)
- Accents are PRESERVED (critical for Spanish accuracy: "año" != "ano")

This tokenizer is a conscious design choice: lexical tokenization avoids the ~40MB
spaCy dependency or ~2GB PyTorch from sentence-transformers for the MVP.
"""

from __future__ import annotations

import re
import unicodedata

# Spanish stopwords — inline to avoid file I/O or external dependency.
# Covers common articles, prepositions, conjunctions, and short pronouns
# that add noise to token overlap statistics.
STOPWORDS: set[str] = {
    "el", "la", "los", "las",
    "un", "una", "unos", "unas",
    "de", "del", "en", "y", "a",
    "que", "es", "por", "con",
    "se", "su", "sus", "para",
    "como", "más", "mas", "pero",
    "le", "ya", "o", "si", "no",
    "esto", "eso", "esta", "este",
    "al", "lo", "entre", "todo",
}


def tokenize(text: str) -> set[str]:
    """Tokenize Spanish text into a set of normalized tokens.

    Returns an empty set for empty, stopword-only, or punctuation-only input.

    The function applies, in order:
    1. NFKC normalization
    2. Lowercase
    3. Punctuation → spaces
    4. Split on whitespace
    5. Filter: min length 3 and not a stopword
    """
    if not text or not text.strip():
        return set()

    text = unicodedata.normalize("NFKC", text)
    text = text.lower()

    # Replace non-word, non-whitespace characters with spaces.
    # \\w in Python (with default re.UNICODE) matches accented letters,
    # so accents are preserved.
    text = re.sub(r"[^\w\s]", " ", text)

    words = text.split()
    return {w for w in words if len(w) >= 3 and w not in STOPWORDS}
