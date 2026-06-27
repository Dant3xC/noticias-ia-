# noticias-ia

Agregador CLI personal de noticias para fuentes RSS argentinas. Contrasta las
coberturas entre medios de distintas posiciones ideológicas, calcula etiquetas
de confianza algorítmicas y utiliza un LLM económico o gratuito para escribir
resúmenes diarios estructurados.

La idea central: **detección de noticias falsas por contraste** — cuando fuentes
de distintas posiciones ideológicas coinciden en los hechos, la historia es más
confiable; cuando divergen, la divergencia se marca y la confianza baja.

## ¿Qué es?

`noticias-ia` es una herramienta de línea de comandos que cada día:

1. **Obtiene** los feeds RSS de las fuentes configuradas (ej: La Izquierda Diario, Infobae, Ámbito, La Nación, Clarín, Derecha Diario).
2. **Agrupa** noticias que hablan del mismo tema en *clústers* o familias de noticias.
3. **Calcula** una etiqueta de confianza (`alta`, `media` o `baja`) basada exclusivamente en la forma del clúster: cantidad de fuentes, diversidad ideológica, y qué tan distintas son las coberturas.
4. **Envía al LLM** solo un JSON compacto por clúster (el *family format*) para que escriba un resumen en español.
5. **Guarda** el resultado del día como una instantánea JSON en `.data/`.
6. **Muestra** los clústers en consola con colores de confianza.

No requiere base de datos, no es un daemon, no necesita GPU. Usa la API de
algún LLM económico (Groq, Gemini o GPT-4o-mini) y procesa todo localmente.

## Instalación

```bash
# Clonar e instalar
git clone https://github.com/Dant3xC/noticias-ia-.git
cd noticias-ia
pip install -e ".[dev]"
```

### Windows

Si ve caracteres acentuados ilegibles (á, é, í, ó, ú) en PowerShell, configure
la variable de entorno `PYTHONUTF8` antes de ejecutar la herramienta:

```powershell
$env:PYTHONUTF8 = 1
```

O agréguela de forma permanente desde Propiedades del sistema → Variables de entorno.
PowerShell 7 y Windows Terminal no requieren esta configuración.

## Configuración del entorno

Copie `.env.example` a `.env` y agregue sus claves de API:

```bash
cp .env.example .env
```

Luego edite `.env` con sus claves reales:

```
GROQ_API_KEY=gsk_su_clave_real
GEMINI_API_KEY=su_clave_real
OPENAI_API_KEY=sk-su_clave_real
```

Se requiere al menos una clave para los resúmenes con LLM. Las tres son
opcionales: la herramienta funciona con cualquier proveedor que configure
y aplica fallback entre ellos:

| Prioridad | Proveedor | Variable de entorno | Modelo |
|-----------|-----------|---------------------|--------|
| 1ª | Groq | `GROQ_API_KEY` | `groq/llama-3.3-70b-versatile` |
| 2ª | Gemini | `GEMINI_API_KEY` | `gemini/gemini-2.0-flash-exp` |
| 3ª | OpenAI | `OPENAI_API_KEY` | `gpt-4o-mini` |

Si no configura ninguna clave, el pipeline funciona igual: los clústers reciben
un resumen plantilla ("Sin resumen disponible") y las etiquetas de confianza
siguen calculándose con normalidad.

## Primera ejecución

La instalación trae 6 fuentes por defecto (distribución 1 izquierda / 2 centro / 3
derecha). Las URLs fueron verificadas y deberían funcionar out-of-the-box:

| Fuente | Línea | URL del feed |
|--------|-------|--------------|
| La Izquierda Diario | left | `http://www.laizquierdadiario.com/spip.php?page=backend_portada` |
| Infobae | center | `https://www.infobae.com/arc/outboundfeeds/rss/argentina/` |
| Ámbito | center | `https://www.ambito.com/rss/home.xml` |
| La Nación | right | `https://www.lanacion.com.ar/arc/outboundfeeds/rss/` |
| Clarín | right | `https://www.clarin.com/rss/lo-ultimo/` |
| Derecha Diario | right | `https://derechadiario.com.ar/rss` |

> **Nota**: Página/12 fue removida de las fuentes por defecto porque su feed RSS
> dejó de funcionar permanentemente. Si lo desea, puede agregarla manualmente con
> `noticias fuentes add pagina12 <url> --lean left`, aunque el feed ya no responde.

### Filtros de contenido y temas

La herramienta incluye dos filtros opcionales que se aplican después de la
obtención y antes de la ventana temporal:

1. **Filtro de contenido** (`--no-filter` para desactivar): elimina noticias de
   entretenimiento (horóscopo, Gran Hermano, farándula, etc.) usando una lista
   de palabras clave configurables.
2. **Filtro de temas** (`--topic`): conserva solo las noticias que coinciden
   con los temas de interés configurados (ej: `--topic economía --topic fútbol`).

Ambos filtros usan coincidencia por subcadena (case-insensitive) sobre el
título + cuerpo de cada noticia.

```bash
# Verificar la versión
python -m noticias --version

# Listar las fuentes configuradas (debería mostrar 6 por defecto)
python -m noticias fuentes list

# Verificar que los feeds responden
python -m noticias health

# Ejecutar el resumen diario (sin LLM, usa resúmenes plantilla)
python -m noticias resumen --no-llm

# Con filtro de contenido desactivado (pasa todo el entretenimiento)
python -m noticias resumen --no-filter

# Solo noticias de economía y fútbol
python -m noticias resumen --topic economía --topic fútbol

# Con LLM (si configuró al menos una clave)
python -m noticias resumen

# Configurar temas persistentes (se aplican en cada ejecución)
python -m noticias fuentes config topics economía fútbol política

# Ver temas configurados
python -m noticias fuentes config topics

# Saltar el filtro de temas explícitamente (incluso con temas persistentes)
python -m noticias resumen --no-topics
```

### Nota sobre fastembed

La primera ejecución del pipeline con clustering semántico descarga
automáticamente el modelo `BAAI/bge-small-multilingual-v1` (~130 MB) al
directorio `~/.cache/fastembed/`. La descarga ocurre una sola vez; las
ejecuciones siguientes usan el modelo en caché. No requiere GPU, pero la
descarga inicial puede tomar unos segundos según su conexión.

Si algún feed se rompe en el futuro, use `noticias fuentes add <nombre> <url> --lean <left|center|right>` para reemplazarlo, o `noticias fuentes remove <nombre>` para sacarlo.

## Uso

| Comando | Descripción |
|---------|-------------|
| `noticias --version` | Mostrar la versión y salir |
| `noticias resumen` | Ejecutar el pipeline completo y obtener el resumen del día |
| `noticias resumen --no-llm` | Saltar el LLM y usar resúmenes plantilla |
| `noticias resumen --since 7d` | Ventana temporal personalizada (ej: `24h`, `7d`, `30m`) |
| `noticias resumen --sources pagina12,clarin` | Filtrar por fuentes específicas |
| `noticias resumen --verbose` | Activar logging DEBUG |
| `noticias fuentes list` | Listar las fuentes configuradas |
| `noticias fuentes add <nombre> <url> --lean <left\|center\|right>` | Agregar una fuente |
| `noticias fuentes remove <nombre>` | Quitar una fuente |
| `noticias fuentes config topics [temas...]` | Configurar temas de interés persistentes (se aplican en cada resumen) |
| `noticias fuentes config topics --clear` | Limpiar la lista de temas persistentes |
| `noticias health` | Verificar el estado HTTP de las fuentes configuradas |
| `noticias snapshot list` | Listar las instantáneas diarias guardadas |
| `noticias snapshot show <archivo>` | Volver a renderizar una instantánea guardada |

### Flags de `noticias resumen`

| Flag | Default | Descripción |
|------|---------|-------------|
| `--since` | `24h` | Ventana temporal. Formato: `Nd` (días), `Nh` (horas), `Nm` (minutos) |
| `--sources` | todas | Nombres de fuentes separados por coma |
| `--no-llm` | `False` | Usar resúmenes plantilla en vez del LLM |
| `--no-filter` | `False` | Desactivar el filtro de contenido (no eliminar entretenimiento) |
| `--no-topics` | `False` | Saltar el filtro de temas (incluso si hay temas persistentes) |
| `--topic` | — | Repetible. Filtrar por temas de interés (ej: `--topic economía --topic fútbol`). Si se usa, anula los temas persistentes de la configuración |
| `--verbose` | `False` | Mostrar logs de depuración |

## ¿Cómo funciona? (Arquitectura)

El pipeline completo tiene etapas que se ejecutan en cada invocación de
`noticias resumen`:

```
[CLI] → [Fetch] → [Content Filter] → [Topic Filter] → [Window] → [Dedup] → [Cluster] → [Family + Trust] → [LLM] → [Persist] → [Render]
```

1. **Fetch**: Obtiene los feeds RSS/Atom de todas las fuentes configuradas en
   paralelo (máx. 5 concurrentes). Cada fuente se obtiene con un rate-limit de
   5 segundos entre requests. Usa un User-Agent de navegador real para evitar
   bloqueos HTTP 403. Si una fuente falla, las demás continúan.

2. **Content Filter**: Elimina noticias de entretenimiento (horóscopo, Gran
   Hermano, farándula, etc.) mediante coincidencia case-insensitive por
   subcadena sobre el título + cuerpo. Desactivable con `--no-filter`.

3. **Topic Filter**: Conserva solo las noticias que coinciden con los temas de
   interés configurados (`--topic` o temas persistentes en `config.json`).
   Coincidencia case-insensitive por subcadena. Saltable con `--no-topics`.

4. **Window**: Filtra por ventana temporal (default 24h). Los ítems sin fecha
   o fuera de la ventana son descartados.

5. **Dedup**: Elimina artículos duplicados o casi duplicados comparando títulos
   (similitud > 0.85) y URLs canónicas (similitud > 0.9). Conserva el ítem más
   antiguo.

6. **Cluster**: Agrupa artículos del mismo evento en clústers usando similitud
   semántica por embeddings (`fastembed`, modelo `BAAI/bge-small-multilingual-v1`,
   ~130 MB). Dos artículos se agrupan si su similitud coseno ≥ 0.85. Como
   fallback para títulos vacíos, usa la similitud de texto (rapidfuzz > 0.75)
   y el patrón de slug en la URL.

7. **Family Format + Trust**: Para cada clúster construye un payload JSON
   compacto (`event_label`, `sources`, `per_source`, `common_facts`,
   `divergences`). Luego calcula la **etiqueta de confianza** de forma 100 %
   algorítmica usando cantidad de fuentes, cantidad de líneas ideológicas
   distintas, y el *divergence ratio* (qué tan distintas son las coberturas).

   | Condición | Etiqueta |
   |-----------|----------|
   | 1 fuente o divergencia ≥ 0.5 | `baja` (rojo) |
   | 2 fuentes, o 1 línea ideológica, o divergencia [0.2, 0.5) | `media` (amarillo) |
   | ≥ 3 fuentes, ≥ 2 líneas ideológicas, divergencia < 0.2 | `alta` (verde) |

8. **LLM Summary**: Envía solo el family format (un JSON pequeño por clúster)
   al LLM para que genere un resumen de 2-3 oraciones en español y hasta 3
   puntos destacados. Si el presupuesto de tokens se agota o el LLM falla, se
   usa un resumen plantilla. **El LLM nunca ve los artículos crudos.**

9. **Persist + Render**: Guarda el resultado como JSON en `.data/YYYY-MM-DD.json`
   y lo muestra en consola con colores (verde=alta, amarillo=media, rojo=baja).

### Family format: el truco que minimiza el costo del LLM

En vez de enviar los artículos completos al LLM (caro y lento), el pipeline
construye por cada clúster un JSON compacto con:

- Un *event label* (etiqueta del evento) derivado de la subcadena común más larga
  entre todos los títulos del clúster
- Las fuentes involucradas y su línea ideológica
- Un extracto del cuerpo por cada fuente
- Hechos comunes y divergencias entre las coberturas

Este payload suele ser de 200-800 caracteres, estimado en ~50-200 tokens, lo
que hace que cada resumen cueste fracciones de centavo incluso en APIs pagas.

## Decisiones de diseño clave

### Trust label 100 % algorítmico

La etiqueta de confianza se calcula exclusivamente a partir de la forma del
clúster: cantidad de fuentes, diversidad ideológica y divergence ratio. **El LLM
no participa en la decisión.** Esto asegura que la confianza sea determinista,
auditable y gratuita de calcular.

### LCS para event labels

Usamos *longest common substring* (subcadena común más larga) entre los títulos
del clúster para generar la etiqueta del evento. Esto evita la dependencia de
spaCy (~40 MB) que requeriría la extracción de sintagmas nominales. La LCS debe
tener ≥ 20 caracteres y ≥ 3 palabras para ser usada; de lo contrario se usa el
primer título del clúster.

### Family format

El LLM solo ve un JSON compacto por clúster, no los artículos crudos. Esto
reduce el costo por resumen a fracciones de centavo y mantiene la privacidad
del contenido original (el LLM nunca recibe el texto completo de los artículos).

### Fake news por contraste

Cuando fuentes de distintas líneas ideológicas (izquierda, centro, derecha)
coinciden en los hechos, la confianza sube. Esta es una estrategia deliberada:
si Página12 y La Nación reportan el mismo hecho con el mismo énfasis, es más
probable que sea verdadero que si solo una fuente lo cubre.

## Solución de problemas

| Problema | Causa probable | Solución |
|----------|---------------|----------|
| Caracteres rotos (á → Ã¡) en PowerShell | Consola en cp1252 | `$env:PYTHONUTF8=1` o usar Windows Terminal |
| `noticias resumen` no trae noticias | URLs de feeds incorrectas | Verifique con `noticias health` |
| `fetch_failures` vacío en la instantánea | Limitación del MVP | Use `noticias health` para verificar fuentes |
| El LLM devuelve respuestas vacías o con error | Clave API faltante o inválida | Verifique `.env` y que la clave tenga crédito |
| Error HTTP 403 (fetch) | Algunas fuentes bloquean User-Agent por defecto | Se envía automáticamente un User-Agent de navegador real. Si persiste, configure `NOTICIAS_USER_AGENT` en `.env` |
| Tests lentos | Suite completa (~350 tests) | Use `pytest -x` (para al primer fallo) o `pytest -k nombre` (uno solo) |

## Desarrollo

```bash
# Tests
pytest                                   # ~360+ tests, ~10s

# Tests por área
pytest tests/unit/                       # tests unitarios (~260)
pytest tests/component/                  # tests de componentes (~70)
pytest tests/integration/                # tests de integración (~5)

# Formato (opcional)
ruff check src/ tests/

# Estructura de directorios
src/noticias/
├── __main__.py          # Entry point: python -m noticias
├── cli/                 # Comandos CLI (app, fuentes, health, snapshot)
├── llm/                 # Cliente LLM, prompt, parser de respuestas
├── models/              # Modelos de datos (msgspec Struct)
├── persistence/         # Config y snapshots (lectura/escritura JSON)
├── pipeline/            # Etapas del pipeline (fetch, cluster, dedup, etc.)
├── render/              # Renderizado en consola con Rich
├── sources/             # Registro de fuentes y adaptadores RSS
└── trust/               # Cálculo algorítmico de etiquetas de confianza
```

## Roadmap / qué NO está

| Funcionalidad | Estado | Para agregarla haría falta |
|--------------|--------|---------------------------|
| Web scraping (fuentes sin RSS) | Fuera de alcance | Scraper por fuente con trafilatura o Playwright |
| Clustering semántico (embeddings) | Implementado | `fastembed` + modo semántico con `BAAI/bge-small-multilingual-v1` |
| Daemon / ejecución programada | Fuera de alcance | APScheduler o tarea programada del sistema |
| Fuentes internacionales | Fuera de alcance | Stopwords multi-lenguaje, Lean extendido |
| Resúmenes multi-idioma | Fuera de alcance | Template de prompt por idioma, flag `--lang` |
| Búsqueda histórica | Fuera de alcance | Índice SQLite sobre instantáneas, comando `noticias search` |
| UI web | Fuera de alcance | Servidor web + API REST + frontend |
| Base de datos (SQLite/PostgreSQL) | Fuera de alcance | Migrar persistencia de JSON a DBMS |
| Política de retención de instantáneas | Fuera de alcance | Módulo de retención, flag `--retain 30d` |

## Licencia

MIT. Proyecto personal de uso público.
