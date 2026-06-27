"""Entry point for `python -m noticias`.

Loads environment variables from .env (if present) before any other module
imports, so the LLM client can read API keys when the user runs the CLI.
Library/programmatic use should call load_dotenv() themselves.

The .env file is located via the shared `noticias._project_root` helper,
so the lookup is robust to the user's CWD.
"""

from dotenv import load_dotenv

from noticias._project_root import project_root

load_dotenv(project_root() / ".env")

from noticias.cli.app import app

app()
