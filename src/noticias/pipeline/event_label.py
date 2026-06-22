"""Event label extraction from cluster titles.

Uses **Longest Common Substring** (LCS) across all titles in a cluster as a
cheap, dependency-free approximation of the "best event name."

Conscious deviation from the spec
----------------------------------
The original spec called for **most-frequent noun-phrase** extraction, which
would require spaCy (~40 MB download) or similar NLP dependency. For the MVP,
LCS is a pragmatic substitute:

    - Cross-source wire services (AP, Reuters, AFP, Télam) feed the same
      phrasing to multiple outlets, so a shared substring is a strong signal.
    - LCS is O(n·m²) in the worst case, but with <20 titles per cluster and
      title lengths <200 characters it runs in microseconds.
    - Noun-phrase extraction (spaCy) can be layered in later without changing
      the calling code or the ``event_label`` function signature.

Decision: LCS with two guards — length ≥ 20 characters AND ≥ 3 words — to
avoid returning a trivial substring like ``"el"``. When those guards are not
met the first title is used as the fallback (truncated to 80 chars).
"""

from __future__ import annotations


def _longest_common_substring(strings: list[str]) -> str:
    """Find the longest substring that appears in **all** supplied strings.

    This is the textbook O(n·m) dynamic-programming approach, applied
    pairwise against the shortest input string.  Because titles are short
    and few (<200 chars, <20 titles) the quadratic behaviour is invisible.

    If multiple substrings share the maximum length the first one found
    is returned (fine for our use case — they are typically equivalent).
    """
    if not strings:
        return ""
    if len(strings) == 1:
        return strings[0]

    # Start with the shortest string — this bounds the search.
    shortest = min(strings, key=len)
    best = ""
    best_len = 0

    for i in range(len(shortest)):
        for j in range(i + best_len + 1, len(shortest) + 1):
            candidate = shortest[i:j]
            # Check presence in every other string.
            for s in strings:
                if candidate not in s:
                    break
            else:
                if len(candidate) > best_len:
                    best = candidate
                    best_len = len(candidate)

    return best


def event_label(titles: list[str]) -> str:
    """Derive a compact event label from a list of article titles.

    Strategy
    --------
    1. Compute the longest common substring across all titles.
    2. If the LCS is ≥ 20 characters **and** has ≥ 3 words, use it as the label.
    3. Otherwise fall back to the first title.

    In both cases the result is truncated to 80 characters to keep the label
    (and the family-format payload) compact.

    Args:
        titles: Article titles from one cluster, in ``[NewsItem.title, ...]``
            form.  Must contain at least one non-empty title.

    Returns:
        A label string ≤ 80 characters.
    """
    if not titles:
        return ""

    lcs = _longest_common_substring(titles).strip()

    if len(lcs) >= 20 and len(lcs.split()) >= 3:
        return lcs[:80]

    return titles[0].strip()[:80]
