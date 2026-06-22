"""Entry point for `python -m noticias`.

Loads environment variables from .env (if present) before any other module
imports, so the LLM client can read API keys when the user runs the CLI.
Library/programmatic use should call load_dotenv() themselves.
"""

from dotenv import load_dotenv

load_dotenv()

from noticias.cli.app import app

app()
