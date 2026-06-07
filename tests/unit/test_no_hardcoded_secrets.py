"""Guard against re-introducing a hardcoded ElevenLabs key.

The legacy ``Hamlet-gen5.py`` shipped with an ElevenLabs API key on line 204.
This test fails loudly if any tracked source file under the project root
contains a literal ``sk_...`` style key. It does NOT scan the leaked key
character-by-character — that key is in git history; the user must rotate it
at ElevenLabs.
"""
from __future__ import annotations

import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent.parent

# ElevenLabs / Anthropic / OpenAI keys all start with a short prefix followed
# by a long base62 blob. We match conservatively to avoid false positives on
# pytest internals.
SECRET_RE = re.compile(r"sk_[A-Za-z0-9]{32,}|sk-[A-Za-z0-9]{32,}|sk-ant-[A-Za-z0-9-]{32,}")

# Skip vendor and metadata folders.
SKIP_DIRS = {".git", ".venv", "venv", "node_modules", "__pycache__", ".idea", "build", "dist"}


def _iter_source_files() -> list[Path]:
    files: list[Path] = []
    for path in REPO_ROOT.rglob("*"):
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if not path.is_file():
            continue
        if path.suffix.lower() not in {".py", ".md", ".toml", ".txt", ".json", ".yaml", ".yml", ""}:
            continue
        # Don't scan ourselves — the regex above counts as a match.
        if path.samefile(Path(__file__)):
            continue
        files.append(path)
    return files


def test_no_hardcoded_api_keys_anywhere():
    hits: list[tuple[Path, str]] = []
    for path in _iter_source_files():
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for match in SECRET_RE.finditer(text):
            hits.append((path.relative_to(REPO_ROOT), match.group(0)[:8] + "…"))
    assert hits == [], f"hardcoded secrets detected: {hits}"
