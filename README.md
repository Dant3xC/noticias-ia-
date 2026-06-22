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

1. **Obtiene** los feeds RSS de las fuentes configuradas (ej: Página12, La Nación, Clarín, Infobae, Ámbito).
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
| 1ª | Groq | `GROQ_API_KEY` | `groq/llama-3.1-8b-instant` |
| 2ª | Gemini | `GEMINI_API_KEY` | `gemini/gemini-2.0-flash-exp` |
| 3ª | OpenAI | `OPENAI_API_KEY` | `gpt-4o-mini` |

Si no configura ninguna clave, el pipeline funciona igual: los clústers reciben
un resumen plantilla ("Sin resumen disponible") y las etiquetas de confianza
siguen calculándose con normalidad.

## Primera ejecución

```bash
# Verificar la versión
python -m noticias --version

# Listar las fuentes configuradas (inicialmente vacío)
python -m noticias fuentes list

# Agregar las fuentes recomendadas
python -m noticias fuentes add pagina12 https://www.pagina12.com.ar/rss/portada --lean left
python -m noticias fuentes add lanacion https://www.lanacion.com.ar/rss/ultimas-noticias/ --lean right
python -m noticias fuentes add clarin https://www.clarin.com/rss/lo-mas-visto/ --lean right
python -m noticias fuentes add infobae https://www.infobae.com/rss/ --lean center
python -m noticias fuentes add ambito https://www.ambito.com/rss/home.xml --lean center

# (Opcional) Agregar fuentes abiertamente partidarias para mejor contraste
# Busque las URLs reales de sus RSS feeds:
python -m noticias fuentes add laizquierdadiario https://laizquierdadiario.com.ar/rss --lean left
python -m noticias fuentes add derechadiario https://derechadiario.com.ar/rss --lean right

# Verificar que las URLs respondan
python -m noticias health

# Ejecutar el resumen diario (sin LLM, usa resúmenes plantilla)
python -m noticias resumen --no-llm

# Con LLM (si configuró al menos una clave)
python -m noticias resumen
```

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
| `noticias health` | Verificar el estado HTTP de las fuentes configuradas |
| `noticias snapshot list` | Listar las instantáneas diarias guardadas |
| `noticias snapshot show <archivo>` | Volver a renderizar una instantánea guardada |

### Flags de `noticias resumen`

| Flag | Default | Descripción |
|------|---------|-------------|
| `--since` | `24h` | Ventana temporal. Formato: `Nd` (días), `Nh` (horas), `Nm` (minutos) |
| `--sources` | todas | Nombres de fuentes separados por coma |
| `--no-llm` | `False` | Usar resúmenes plantilla en vez del LLM |
| `--verbose` | `False` | Mostrar logs de depuración |

## ¿Cómo funciona? (Arquitectura)

El pipeline completo tiene 7 etapas que se ejecutan en cada invocación de
`noticias resumen`:

```
[CLI] → [Fetch] → [Normalize] → [Dedup] → [Cluster] → [Family Format + Trust] → [LLM] → [Persist] → [Render]
```

1. **Fetch**: Obtiene los feeds RSS/Atom de todas las fuentes configuradas en
   paralelo (máx. 5 concurrentes). Cada fuente se obtiene con un rate-limit de
   5 segundos entre requests. Si una fuente falla, las demás continúan.

2. **Normalize**: Convierte cada ítem del feed a un formato común
   (`title`, `url`, `source`, `published_at`, `body`). Soporta RSS 2.0 y Atom.
   Si no hay cuerpo (`body`), usa el título como fallback.

3. **Dedup**: Elimina artículos duplicados o casi duplicados comparando títulos
   (similitud > 0.85) y URLs canónicas (similitud > 0.9). Conserva el ítem más
   antiguo.

4. **Cluster**: Agrupa artículos del mismo evento en clústers. Dos artículos
   pertenecen al mismo clúster si la similitud de sus títulos > 0.75 o si
   comparten dominio y patrón de slug en la URL.

5. **Family Format + Trust**: Para cada clúster construye un payload JSON
   compacto (`event_label`, `sources`, `per_source`, `common_facts`,
   `divergences`). Luego calcula la **etiqueta de confianza** de forma 100 %
   algorítmica usando cantidad de fuentes, cantidad de líneas ideológicas
   distintas, y el *divergence ratio* (qué tan distintas son las coberturas).

   | Condición | Etiqueta |
   |-----------|----------|
   | 1 fuente o divergencia ≥ 0.5 | `baja` (rojo) |
   | 2 fuentes, o 1 línea ideológica, o divergencia [0.2, 0.5) | `media` (amarillo) |
   | ≥ 3 fuentes, ≥ 2 líneas ideológicas, divergencia < 0.2 | `alta` (verde) |

6. **LLM Summary**: Envía solo el family format (un JSON pequeño por clúster)
   al LLM para que genere un resumen de 2-3 oraciones en español y hasta 3
   puntos destacados. Si el presupuesto de tokens se agota o el LLM falla, se
   usa un resumen plantilla. **El LLM nunca ve los artículos crudos.**

7. **Persist + Render**: Guarda el resultado como JSON en `.data/YYYY-MM-DD.json`
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
| Tests lentos | Suite completa (~300 tests) | Use `pytest -x` (para al primer fallo) o `pytest -k nombre` (uno solo) |

## Desarrollo

```bash
# Tests
pytest                                   # ~300 tests, ~7s

# Tests por área
pytest tests/unit/                       # tests unitarios (~220)
pytest tests/component/                  # tests de componentes (~60)
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
| Clustering semántico (embeddings) | Fuera de alcance | `fastembed` + modo semántico en el clusterizador |
| Daemon / ejecución programada | Fuera de alcance | APScheduler o tarea programada del sistema |
| Fuentes internacionales | Fuera de alcance | Stopwords multi-lenguaje, Lean extendido |
| Resúmenes multi-idioma | Fuera de alcance | Template de prompt por idioma, flag `--lang` |
| Búsqueda histórica | Fuera de alcance | Índice SQLite sobre instantáneas, comando `noticias search` |
| UI web | Fuera de alcance | Servidor web + API REST + frontend |
| Base de datos (SQLite/PostgreSQL) | Fuera de alcance | Migrar persistencia de JSON a DBMS |
| Política de retención de instantáneas | Fuera de alcance | Módulo de retención, flag `--retain 30d` |

## Licencia

MIT. Proyecto personal de uso público.
