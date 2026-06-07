"""Persistent on-disk library of recent voice clones.

JSON file at ``cfg.voice_clone.voice_library_path`` storing a list of voice
entries with the original sample path plus consent + retention metadata so the
operator can recall any past volunteer in the GUI, prove consent, and sweep
expired clones (locally and from ElevenLabs). Atomic writes (``.tmp`` +
``os.replace``) protect the file from corruption.
"""
from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


VALID_RETENTION_POLICIES = {"keep", "ephemeral", "delete_after_show"}


@dataclass(frozen=True)
class VoiceEntry:
    voice_id: str
    label: str
    created_at: str  # ISO 8601 UTC
    sample_path: str  # absolute path string
    sample_filename: str
    # --- consent + retention (Step 4) -------------------------------------
    consent_confirmed: bool = False
    consent_timestamp: str | None = None
    retention_policy: str = "keep"  # one of VALID_RETENTION_POLICIES
    remote_deleted: bool = False
    provider_metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def new(
        cls,
        voice_id: str,
        label: str,
        sample_path: str,
        sample_filename: str,
        *,
        consent_confirmed: bool = False,
        consent_timestamp: str | None = None,
        retention_policy: str = "keep",
        remote_deleted: bool = False,
        provider_metadata: dict[str, Any] | None = None,
        now: datetime | None = None,
    ) -> "VoiceEntry":
        ts = (now or datetime.now(timezone.utc)).isoformat(timespec="seconds")
        return cls(
            voice_id=voice_id,
            label=label,
            created_at=ts,
            sample_path=sample_path,
            sample_filename=sample_filename,
            consent_confirmed=consent_confirmed,
            consent_timestamp=consent_timestamp,
            retention_policy=retention_policy,
            remote_deleted=remote_deleted,
            provider_metadata=provider_metadata or {},
        )


def _parse_iso(ts: str) -> datetime | None:
    try:
        dt = datetime.fromisoformat(ts)
    except (ValueError, TypeError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


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
                        # New fields tolerate older files lacking them.
                        consent_confirmed=bool(item.get("consent_confirmed", False)),
                        consent_timestamp=item.get("consent_timestamp"),
                        retention_policy=item.get("retention_policy", "keep"),
                        remote_deleted=bool(item.get("remote_deleted", False)),
                        provider_metadata=item.get("provider_metadata") or {},
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

    # ---- deletion + sweep (Step 4) ---------------------------------------

    def delete_local(self, voice_id: str) -> bool:
        """Remove the entry from the local library only. Returns True if removed."""
        return self.remove(voice_id)

    def delete_remote(self, voice_id: str, client) -> bool:
        """Delete the voice from ElevenLabs and mark the entry ``remote_deleted``.

        Returns True if the remote delete succeeded (and the entry was updated).
        """
        entry = self.get(voice_id)
        if entry is None:
            return False
        client.delete_voice(voice_id)
        entries = self.load()
        updated = [
            e if e.voice_id != voice_id else _mark_remote_deleted(e)
            for e in entries
        ]
        self.save(updated)
        return True

    def delete_both(self, voice_id: str, client) -> bool:
        """Delete remotely (ElevenLabs) then locally. Returns True if entry existed."""
        if self.get(voice_id) is None:
            return False
        self.delete_remote(voice_id, client)
        self.delete_local(voice_id)
        return True

    def sweep_expired(self, now: datetime, retention, client=None) -> list[str]:
        """Delete every entry whose retention policy says it has expired.

        ``retention`` is a :class:`hamlet_ai.config.RetentionSettings`. ``client``
        (optional) lets the sweep also delete the remote ElevenLabs voice. Returns
        the list of removed voice_ids.
        """
        removed: list[str] = []
        for entry in self.load():
            if not _is_expired(entry, now, retention):
                continue
            if client is not None and not entry.remote_deleted:
                try:
                    client.delete_voice(entry.voice_id)
                except Exception:  # noqa: BLE001 — best-effort remote cleanup
                    pass
            self.delete_local(entry.voice_id)
            removed.append(entry.voice_id)
        return removed


def _mark_remote_deleted(entry: VoiceEntry) -> VoiceEntry:
    from dataclasses import replace

    return replace(entry, remote_deleted=True)


def _is_expired(entry: VoiceEntry, now: datetime, retention) -> bool:
    policy = entry.retention_policy
    if policy == "keep":
        return False
    if policy == "ephemeral":
        return True
    if policy == "delete_after_show":
        created = _parse_iso(entry.created_at)
        if created is None:
            return False
        age_hours = (now - created).total_seconds() / 3600.0
        return age_hours >= retention.delete_after_show_ttl_hours
    return False
