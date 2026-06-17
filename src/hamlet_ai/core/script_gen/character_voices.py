"""Persistent character → ElevenLabs voice_id map for Script Gen.

JSON layout::

    {
      "HAMLET":   "KVvlsr2Tb3CgvisbEDHy",
      "_default": "TUKJhQmz3RPYBNAgC5A1"
    }

The ``_default`` entry is used when a detected character has no explicit
mapping. The shipped default is a single German voice used for the whole
scene; add per-character entries here or via voices.json to override it.
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path


LEGACY_DEFAULT_MAP: dict[str, str] = {
    # German voice for the Wember / Wolf359 ghost lines. Every character falls
    # through to _default (resolve() does this when a character has no explicit
    # entry), so one valid German voice covers the whole scene. The previous
    # per-character IDs pointed at a retired ElevenLabs account and 404'd.
    "_default": "TUKJhQmz3RPYBNAgC5A1",
}


class CharacterVoiceMap:
    def __init__(self, path: Path):
        self.path = path

    def load(self) -> dict[str, str]:
        if not self.path.exists():
            return dict(LEGACY_DEFAULT_MAP)
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return dict(LEGACY_DEFAULT_MAP)
        if not isinstance(raw, dict):
            return dict(LEGACY_DEFAULT_MAP)
        # Ensure _default is always present
        merged = {**LEGACY_DEFAULT_MAP, **{k: str(v) for k, v in raw.items() if isinstance(v, str)}}
        return merged

    def save(self, mapping: dict[str, str]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(
            prefix=".voices-", suffix=".json", dir=self.path.parent
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(mapping, fh, indent=2, sort_keys=True)
            os.replace(tmp_name, self.path)
        except Exception:
            try:
                os.unlink(tmp_name)
            except FileNotFoundError:
                pass
            raise

    def resolve(self, character: str, overrides: dict[str, str] | None = None) -> str:
        """Return voice_id for ``character``, consulting overrides first.

        ``overrides`` is per-run in-memory state (e.g. per-line voice picks).
        Lookup order: overrides[char] → loaded[char] → loaded[_default].
        """
        loaded = self.load()
        if overrides and character in overrides:
            return overrides[character]
        if character in loaded:
            return loaded[character]
        return loaded["_default"]
