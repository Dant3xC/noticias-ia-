# noticias-ia

Agregador CLI personal de noticias para fuentes RSS argentinas. Contrasta las
coberturas entre medios de distintas posiciones ideológicas, calcula etiquetas
de confianza algorítmicas y utiliza un LLM económico o gratuito para escribir
resúmenes diarios estructurados.

La idea central: **detección de noticias falsas por contraste**: cuando fuentes
de distintas posiciones ideológicas coinciden en los hechos, la historia es más
confiable; cuando divergen, la divergencia se marca.

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
y aplica fallback entre ellos.

## Primera ejecución

```bash
# Verificar la versión
python -m noticias --version

# Listar las fuentes configuradas (inicialmente vacío)
python -m noticias fuentes list

# Agregar las dos fuentes abiertamente partidarias recomendadas
# (las URLs del RSS son marcadores: reemplácelas con las URLs reales del feed):
noticias fuentes add laizquierdadiario https://laizquierdadiario.com.ar/rss --lean left
noticias fuentes add derechadiario https://derechadiario.com.ar/rss --lean right

# Ejecutar el resumen diario
noticias resumen
```

## Uso

| Comando | Descripción |
|---------|-------------|
| `noticias fuentes list` | Listar las fuentes configuradas |
| `noticias fuentes add <nombre> <url> --lean left\|center\|right` | Agregar una fuente. Valores de `--lean`: `left` (izquierda), `center` (centro), `right` (derecha) |
| `noticias fuentes remove <nombre>` | Quitar una fuente |
| `noticias resumen` | Ejecutar el pipeline completo y obtener el resumen del día |
| `noticias health` | Verificación previa del estado de las fuentes |
| `noticias snapshot list` | Listar las instantáneas diarias |
| `noticias snapshot show <archivo>` | Volver a renderizar una instantánea guardada |

## Notas de diseño

Las etiquetas de evento utilizan la subcadena común más larga (LCS) entre los
títulos del clúster, con fallback al primer título del ítem. Esto evita la
dependencia de spaCy (~40 MB) que requeriría la extracción de sintagmas
nominales. Se requiere que la LCS tenga ≥ 20 caracteres Y ≥ 3 palabras para
ser utilizada; de lo contrario, se usa el primer título como etiqueta.
