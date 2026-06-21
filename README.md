# noticias-ia

A personal CLI news aggregator for Argentinian RSS sources. Cross-references stories
across outlets from different ideological positions, computes algorithmic trust labels,
and uses a cheap/free LLM to write structured daily summaries.

The core insight: **fake news detection by contrast** — when sources from different
ideological positions agree on facts, the story is more trustworthy; when they diverge,
the divergence is flagged.

## Install

```bash
# Clone and install
git clone https://github.com/Dant3xC/noticias-ia-.git
cd noticias-ia
pip install -e ".[dev]"
```

### Windows

If you see garbled accented characters (á, é, í, ó, ú) in PowerShell, set the
`PYTHONUTF8` environment variable before running the tool:

```powershell
$env:PYTHONUTF8 = 1
```

Or add it permanently via System Properties → Environment Variables.

## Environment Setup

Copy `.env.example` to `.env` and add your API keys:

```bash
cp .env.example .env
```

Then edit `.env` with your actual API keys:

```
GROQ_API_KEY=gsk_your_actual_key
GEMINI_API_KEY=your_actual_key
OPENAI_API_KEY=sk-your_actual_key
```

At least one key is required for LLM summaries. All three are optional — the tool
will work with whatever provider(s) you configure and fall back between them.

## First Run

```bash
# Check the version
python -m noticias --version

# List configured sources (initially empty)
python -m noticias fuentes list

# Add the two recommended openly-partisan sources (their RSS URLs are placeholders —
# replace with the actual feed URLs):
noticias fuentes add laizquierdadiario https://laizquierdadiario.com.ar/rss --lean left
noticias fuentes add derechadiario https://derechadiario.com.ar/rss --lean right

# Now run the daily summary
noticias resumen
```

## Usage

| Command | Description |
|---------|-------------|
| `noticias fuentes list` | List configured sources |
| `noticias fuentes add <name> <url> --lean left\|center\|right` | Add a source |
| `noticias fuentes remove <name>` | Remove a source |
| `noticias resumen` | Run the full pipeline and get today's news summary |
| `noticias health` | Pre-flight check on all sources |
| `noticias snapshot list` | List daily snapshots |
| `noticias snapshot show <file>` | Re-render a stored snapshot |

## Design Notes

Event labels use Longest Common Substring (LCS) across cluster titles, with
fallback to the first item's title. This avoids the ~40MB spaCy dependency that
noun-phrase extraction would require. LCS ≥ 20 characters AND ≥ 3 words is
required to be used; otherwise the first title serves as the label.
