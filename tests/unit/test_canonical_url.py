"""Unit tests for URL canonicalisation (pipeline/dedup.py).

Covers:
- www stripping
- Trailing slash stripping
- Host lowercasing
- Tracking param removal (utm_*, fbclid, gclid)
- Empty URL
"""

from __future__ import annotations

from noticias.pipeline.dedup import canonical_url


class TestCanonicalURL:
    def test_www_stripped(self) -> None:
        assert canonical_url("https://www.example.com/path") == "https://example.com/path"

    def test_no_www_unchanged(self) -> None:
        assert canonical_url("https://example.com/path") == "https://example.com/path"

    def test_trailing_slash_stripped(self) -> None:
        assert canonical_url("https://example.com/path/") == "https://example.com/path"

    def test_root_path_preserved(self) -> None:
        """Root path '/' should stay, not become empty."""
        result = canonical_url("https://example.com")
        assert result == "https://example.com/"

    def test_host_lowercased(self) -> None:
        assert canonical_url("https://Example.COM/Path") == "https://example.com/Path"

    def test_utm_source_stripped(self) -> None:
        result = canonical_url("https://example.com/page?utm_source=twitter&utm_medium=social")
        assert "utm_source" not in result
        assert "utm_medium" not in result

    def test_fbclid_stripped(self) -> None:
        result = canonical_url("https://example.com/page?fbclid=abc123&keep=val")
        assert "fbclid" not in result
        assert "keep=val" in result

    def test_gclid_stripped(self) -> None:
        result = canonical_url("https://example.com/page?gclid=xyz")
        assert result == "https://example.com/page"

    def test_all_tracking_stripped(self) -> None:
        url = "https://www.example.com/story/?utm_campaign=summer&fbclid=abc&gclid=xyz&ref=news"
        result = canonical_url(url)
        assert "utm_campaign" not in result
        assert "fbclid" not in result
        assert "gclid" not in result
        assert "ref" not in result
        # www stripped, trailing slash stripped
        assert result.startswith("https://example.com/story")

    def test_empty_url(self) -> None:
        assert canonical_url("") == ""

    def test_fragment_stripped(self) -> None:
        result = canonical_url("https://example.com/page#section")
        assert "#" not in result

    def test_port_preserved(self) -> None:
        result = canonical_url("https://example.com:8080/path")
        assert ":8080" in result

    def test_https_and_http_differ(self) -> None:
        """HTTPS and HTTP should produce different canonical URLs (different schemes)."""
        https = canonical_url("https://example.com/page")
        http = canonical_url("http://example.com/page")
        assert https != http
