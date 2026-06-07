"""Persistent on-disk library of recent voice clones.

JSON file at ``cfg.voice_clone.voice_library_path`` storing a list of voice
entries with the original sample path so the operator can recall any past
volunteer in the GUI. Atomic writes (``.tmp`` + ``os.replace``) protect the
file from corruption.
"""
from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


@dataclass(frozen=True)
class VoiceEntry:
    voice_id: str
    label: str
    created_at: str  # ISO 8601 UTC
    sample_path: str  # absolute path string
    sample_filename: str

    @classmethod
    def new(
        cls,
        voice_id: str,
        label: str,
        sample_path: str,
        sample_filename: str,
        now: datetime | None = None,
    ) -> "VoiceEntry":
        ts = (now or datetime.now(timezone.utc)).isoformat(timespec="seconds")
        return cls(
            voice_id=voice_id,
            label=label,
            created_at=ts,
            sample_path=sample_path,
            sample_filename=sample_filename,
        )


class VoiceLibrary:
    def __init__(self, path: Path):
        self.path = path

    def load(self) -> list[VoiceEntry]:
        if not self.path.exists():
            return []
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []
        if not isinstance(raw, list):
            return []
        out: list[VoiceEntry] = []
        for item in raw:
            if not isinstance(item, dict):
                continue
            try:
                out.append(
                    VoiceEntry(
                        voice_id=item["voice_id"],
                        label=item["label"],
                        created_at=item["created_at"],
                        sample_path=item["sample_path"],
                        sample_filename=item["sample_filename"],
                    )
                )
            except KeyError:
                continue
        return out

    def save(self, entries: Iterable[VoiceEntry]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = [asdict(e) for e in entries]
        fd, tmp_name = tempfile.mkstemp(prefix=".voice-lib-", suffix=".json", dir=self.path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(payload, fh, indent=2)
            os.replace(tmp_name, self.path)
        except Exception:
            try:
                os.unlink(tmp_name)
            except FileNotFoundError:
                pass
            raise

    def add(self, entry: VoiceEntry) -> None:
        entries = self.load()
        # If the voice_id already exists, replace it
        entries = [e for e in entries if e.voice_id != entry.voice_id]
        entries.insert(0, entry)
        self.save(entries)

    def remove(self, voice_id: str) -> bool:
        entries = self.load()
        kept = [e for e in entries if e.voice_id != voice_id]
        if len(kept) == len(entries):
            return False
        self.save(kept)
        return True

    def get(self, voice_id: str) -> VoiceEntry | None:
        for e in self.load():
            if e.voice_id == voice_id:
                return e
        return None

    def list(self) -> list[VoiceEntry]:
        """Return entries newest-first by created_at."""
        entries = self.load()
        return sorted(entries, key=lambda e: e.created_at, reverse=True)
