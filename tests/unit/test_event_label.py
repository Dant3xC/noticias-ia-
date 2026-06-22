"""Unit tests for event label extraction (pipeline/event_label.py).

Covers:
- Longest common substring extraction with multiple titles
- Fallback to first title when LCS is too short
- 80-character truncation
- All-conditions-met for LCS
- None-conditions-met (fallback)
- Single title
- Empty input
"""

from __future__ import annotations

from noticias.pipeline.event_label import event_label


class TestEventLabel:
    def test_lcs_extracted(self) -> None:
        """Titles sharing a substantial substring → LCS is used."""
        titles = [
            "Corte Suprema falla a favor de la libertad de expresión",
            "La Corte Suprema falló a favor de la libertad de expresión",
            "Fallo de la Corte Suprema por libertad de expresión",
        ]
        label = event_label(titles)
        # "libertad de expresión" is shared but let's check the actual LCS
        assert len(label) >= 20
        assert len(label.split()) >= 3
        assert "libertad" in label or "Corte" in label or "expresión" in label

    def test_short_lcs_falls_back_to_first_title(self) -> None:
        """When LCS < 20 chars or < 3 words → first title is used."""
        titles = [
            "Noticia de última hora: terremoto en Japón",
            "Terremoto sacude la costa de Japón",
            "Fuerte sismo en Japón deja daños materiales",
        ]
        label = event_label(titles)
        # LCS might be "Japón" (5 chars) which is < 20 chars → fallback
        assert label == titles[0][:80]

    def test_fallback_to_first_title(self) -> None:
        """No common substring → first title returned."""
        titles = [
            "El gobierno anuncia nuevas medidas económicas",
            "La selección argentina ganó el partido",
            "Clima: alerta por tormentas en el AMBA",
        ]
        label = event_label(titles)
        assert label == titles[0][:80]

    def test_eighty_char_truncation(self) -> None:
        """Label is truncated to 80 characters."""
        long_title = "A" * 200
        titles = [long_title]
        label = event_label(titles)
        assert len(label) == 80

    def test_lcs_truncated_to_eighty(self) -> None:
        """Even when LCS is used, it's capped at 80 chars."""
        long_title = "X" * 200
        titles = [long_title, long_title]  # identical → LCS = 200 chars
        label = event_label(titles)
        assert len(label) == 80

    def test_empty_titles(self) -> None:
        assert event_label([]) == ""

    def test_single_title(self) -> None:
        title = "El gobierno anunció un nuevo plan económico"
        label = event_label([title])
        assert label == title

    def test_titles_with_spaces(self) -> None:
        """Leading/trailing whitespace is stripped from the label."""
        titles = ["  Espacios alrededor  "]
        label = event_label(titles)
        assert label == "Espacios alrededor"
