"""Manual smoke test for noticias CLI.

Run with: python scripts/smoke.py
Exits 0 if all checks pass, 1 otherwise.
"""

from __future__ import annotations

import subprocess
import sys

CHECKS: list[tuple[str, list[str], str]] = [
    ("Version", ["python", "-m", "noticias", "--version"], "noticias-ia"),
    ("Help", ["python", "-m", "noticias", "--help"], "Agregador CLI"),
    ("Fuentes list", ["python", "-m", "noticias", "fuentes", "list"], ""),
    ("Health", ["python", "-m", "noticias", "health"], ""),
]


def run_check(name: str, cmd: list[str], expected_in_output: str) -> bool:
    """Run a command and check exit code + expected substring."""
    result = subprocess.run(cmd, capture_output=True, text=True)
    ok = result.returncode == 0 and (
        not expected_in_output
        or expected_in_output in result.stdout + result.stderr
    )
    print(f"{'OK' if ok else 'FAIL'}: {name}")
    return ok


def main() -> int:
    """Run all smoke checks and return exit code."""
    failures = 0
    for name, cmd, expected in CHECKS:
        if not run_check(name, cmd, expected):
            failures += 1
    if failures:
        print(f"\n{failures} check(s) failed")
        return 1
    print("\nAll smoke checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
