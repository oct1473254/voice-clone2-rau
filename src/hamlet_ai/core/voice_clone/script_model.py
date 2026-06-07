"""Editable in-memory model of ``clone.txt`` for the Voice Clone GUI.

The serialized form must round-trip through ``pipeline.parse_script``: each
entry is ``filename\\ntext`` and entries are separated by exactly ``\\n\\n``.
Atomic writes (``.tmp`` + ``os.replace``) so QLab never reads a partial file.
"""
from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


@dataclass
class ScriptEntry:
    filename: str
    text: str


class ScriptDocument:
    def __init__(self, path: Path):
        self.path = path
        self._entries: list[ScriptEntry] = []

    @property
    def entries(self) -> list[ScriptEntry]:
        return list(self._entries)

    def __len__(self) -> int:
        return len(self._entries)

    def load(self) -> list[ScriptEntry]:
        if not self.path.exists():
            self._entries = []
            return list(self._entries)
        content = self.path.read_text(encoding="utf-8")
        blocks = [b.strip() for b in content.split("\n\n") if b.strip()]
        entries: list[ScriptEntry] = []
        for block in blocks:
            parts = block.split("\n", 1)
            if len(parts) == 2:
                entries.append(ScriptEntry(filename=parts[0].strip(), text=parts[1].strip()))
        self._entries = entries
        return list(self._entries)

    def save(self, entries: Iterable[ScriptEntry] | None = None) -> None:
        if entries is not None:
            self._entries = list(entries)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        serialized = "\n\n".join(f"{e.filename}\n{e.text}" for e in self._entries)
        if serialized:
            serialized += "\n"

        fd, tmp_name = tempfile.mkstemp(prefix=".clone-", suffix=".txt", dir=self.path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(serialized)
            os.replace(tmp_name, self.path)
        except Exception:
            try:
                os.unlink(tmp_name)
            except FileNotFoundError:
                pass
            raise

    def update(self, index: int, entry: ScriptEntry) -> None:
        self._entries[index] = entry

    def insert(self, index: int, entry: ScriptEntry) -> None:
        self._entries.insert(index, entry)

    def append(self, entry: ScriptEntry) -> None:
        self._entries.append(entry)

    def delete(self, index: int) -> None:
        del self._entries[index]
