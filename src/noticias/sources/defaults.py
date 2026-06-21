"""Default source definitions for the MVP.

5 confirmed sources with hardcoded RSS URLs, plus 2 openly partisan sources
whose RSS URLs the user adds on first run via `noticias fuentes add`.
"""

from noticias.models.source import Lean, Source

# 5 MVP sources with confirmed RSS URLs
MVP_SOURCES: list[Source] = [
    Source(
        name="pagina12",
        url="https://www.pagina12.com.ar/rss/portada",
        lean=Lean.LEFT,
    ),
    Source(
        name="lanacion",
        url="https://www.lanacion.com.ar/rss/ultimas-noticias/",
        lean=Lean.RIGHT,
    ),
    Source(
        name="clarin",
        url="https://www.clarin.com/rss/lo-mas-visto/",
        lean=Lean.RIGHT,
    ),
    Source(
        name="infobae",
        url="https://www.infobae.com/rss/",
        lean=Lean.CENTER,
    ),
    Source(
        name="ambito",
        url="https://www.ambito.com/rss/home.xml",
        lean=Lean.CENTER,
    ),
]

# 2 openly partisan sources (amendment) — user provides RSS URL on first run.
# La Izquierda Diario (Trotskyist left) and Derecha Diario (right-libertarian)
# create the strongest possible truth signal: when opposite biases agree on a fact,
# the cross-ideology agreement is maximally trustworthy.
ADDITIONAL_SOURCES: list[Source] = [
    Source(
        name="laizquierdadiario",
        url="",
        lean=Lean.LEFT,
    ),
    Source(
        name="derechadiario",
        url="",
        lean=Lean.RIGHT,
    ),
]

# Combined list of all default sources (5 hardcoded + 2 user-configurable)
DEFAULT_SOURCES: list[Source] = MVP_SOURCES + ADDITIONAL_SOURCES
