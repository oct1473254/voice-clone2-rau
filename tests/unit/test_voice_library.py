"""Step 4: VoiceLibrary persistence, atomic writes, ordering."""
from __future__ import annotations

import json
from datetime import datetime, timezone, timedelta

import pytest

from hamlet_ai.core.voice_clone.voice_library import VoiceEntry, VoiceLibrary


def _entry(voice_id: str, label: str, created_at: str) -> VoiceEntry:
    return VoiceEntry(
        voice_id=voice_id,
        label=label,
        created_at=created_at,
        sample_path=f"/tmp/{voice_id}.mp3",
        sample_filename=f"{voice_id}.mp3",
    )


def test_load_empty_returns_empty_list(tmp_path):
    lib = VoiceLibrary(tmp_path / "voices.json")
    assert lib.load() == []


def test_load_malformed_json_returns_empty(tmp_path):
    path = tmp_path / "voices.json"
    path.write_text("{not valid")
    lib = VoiceLibrary(path)
    assert lib.load() == []


def test_save_then_load_round_trip(tmp_path):
    lib = VoiceLibrary(tmp_path / "voices.json")
    entries = [
        _entry("v1", "Burt", "2026-06-07T19:30:42+00:00"),
        _entry("v2", "Alice", "2026-06-07T20:00:00+00:00"),
    ]
    lib.save(entries)
    loaded = lib.load()
    assert {e.voice_id for e in loaded} == {"v1", "v2"}


def test_add_inserts_at_front_and_keeps_recents(tmp_path):
    lib = VoiceLibrary(tmp_path / "voices.json")
    lib.add(_entry("v1", "First", "2026-06-07T19:00:00+00:00"))
    lib.add(_entry("v2", "Second", "2026-06-07T20:00:00+00:00"))
    raw = json.loads((tmp_path / "voices.json").read_text())
    assert raw[0]["voice_id"] == "v2"
    assert raw[1]["voice_id"] == "v1"


def test_add_replaces_existing_voice_id(tmp_path):
    lib = VoiceLibrary(tmp_path / "voices.json")
    lib.add(_entry("v1", "Old label", "2026-06-07T19:00:00+00:00"))
    lib.add(_entry("v1", "New label", "2026-06-07T20:00:00+00:00"))
    entries = lib.load()
    assert len(entries) == 1
    assert entries[0].label == "New label"


def test_remove_returns_true_when_removed(tmp_path):
    lib = VoiceLibrary(tmp_path / "voices.json")
    lib.add(_entry("v1", "First", "2026-06-07T19:00:00+00:00"))
    assert lib.remove("v1") is True
    assert lib.load() == []


def test_remove_missing_returns_false(tmp_path):
    lib = VoiceLibrary(tmp_path / "voices.json")
    assert lib.remove("doesnotexist") is False


def test_get_returns_entry_or_none(tmp_path):
    lib = VoiceLibrary(tmp_path / "voices.json")
    e = _entry("v1", "Burt", "2026-06-07T19:00:00+00:00")
    lib.add(e)
    assert lib.get("v1") == e
    assert lib.get("nope") is None


def test_list_returns_newest_first(tmp_path):
    lib = VoiceLibrary(tmp_path / "voices.json")
    lib.save([
        _entry("v1", "Old", "2026-06-01T00:00:00+00:00"),
        _entry("v2", "Newest", "2026-06-07T00:00:00+00:00"),
        _entry("v3", "Middle", "2026-06-05T00:00:00+00:00"),
    ])
    listed = lib.list()
    assert [e.voice_id for e in listed] == ["v2", "v3", "v1"]


def test_save_is_atomic(tmp_path, monkeypatch):
    lib = VoiceLibrary(tmp_path / "voices.json")
    lib.add(_entry("v1", "First", "2026-06-07T19:00:00+00:00"))
    before = (tmp_path / "voices.json").read_text()

    def boom(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr("os.replace", boom)
    with pytest.raises(OSError):
        lib.save([_entry("v2", "Boom", "2026-06-07T20:00:00+00:00")])
    # Original file untouched
    assert (tmp_path / "voices.json").read_text() == before
    # No tmp leftover
    leftover = list(tmp_path.glob(".voice-lib-*"))
    assert leftover == [], leftover


def test_voiceentry_new_helper_sets_iso_timestamp():
    now = datetime(2026, 6, 7, 19, 30, 42, tzinfo=timezone.utc)
    e = VoiceEntry.new(
        voice_id="v1",
        label="Burt",
        sample_path="/tmp/burt.mp3",
        sample_filename="burt.mp3",
        now=now,
    )
    assert e.created_at == "2026-06-07T19:30:42+00:00"
