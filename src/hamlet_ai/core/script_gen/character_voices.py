"""Persistent character → ElevenLabs voice_id map for Script Gen.

JSON layout::

    {
      "HAMLET":   "KVvlsr2Tb3CgvisbEDHy",
      "GERTRUDE": "74gFutvuL77B9bbrUgOO",
      "_default": "Q9YXNHUieMKkNdy2cG6m"
    }

The ``_default`` entry is used when a detected character has no explicit
mapping. Initial defaults match the historical hardcoded mapping in
``Hamlet-gen5.py`` so existing shows keep their familiar voices.
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path


LEGACY_DEFAULT_MAP: dict[str, str] = {
    "HAMLET": "KVvlsr2Tb3CgvisbEDHy",
    "GERTRUDE": "74gFutvuL77B9bbrUgOO",
    "POLONIUS": "1RowW8ZFuVniHZV7vBo4",
    "_default": "Q9YXNHUieMKkNdy2cG6m",
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
