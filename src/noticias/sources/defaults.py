"""Default source definitions for the MVP.

6 Argentinian RSS sources with verified URLs. The mix is designed to
maximize ideological diversity so the cross-source contrast algorithm
produces meaningful trust labels: when openly partisan outlets from
opposite ends of the spectrum agree on a fact, the cross-ideology
agreement is the strongest possible truth signal.

Lean distribution:
- left:        laizquierdadiario (1)
- center:      infobae, ambito             (2)
- right:       lanacion, clarin, derechadiario (3)

pagina12 was removed because its RSS feed was permanently taken down
(all ``/rss/*`` variants return 404 as of 2026-06).
"""

from noticias.models.source import Lean, Source


# All URLs were verified by direct HTTP fetch on 2026-06-22.
# If a feed breaks in the future, remove the source and add a working
# replacement via `noticias fuentes add <name> <url> --lean <lean>`.
DEFAULT_SOURCES: list[Source] = [
    # --- left ---
    Source(
        name="laizquierdadiario",
        url="http://www.laizquierdadiario.com/spip.php?page=backend_portada",
        lean=Lean.LEFT,
    ),
    # --- center ---
    Source(
        name="infobae",
        url="https://www.infobae.com/arc/outboundfeeds/rss/argentina/",
        lean=Lean.CENTER,
    ),
    Source(
        name="ambito",
        url="https://www.ambito.com/rss/home.xml",
        lean=Lean.CENTER,
    ),
    # --- right ---
    Source(
        name="lanacion",
        url="https://www.lanacion.com.ar/arc/outboundfeeds/rss/",
        lean=Lean.RIGHT,
    ),
    Source(
        name="clarin",
        url="https://www.clarin.com/rss/lo-ultimo/",
        lean=Lean.RIGHT,
    ),
    Source(
        name="derechadiario",
        url="https://derechadiario.com.ar/rss",
        lean=Lean.RIGHT,
    ),
]
