"""Step 6: CharacterVoiceMap persistence and resolution with overrides."""
from __future__ import annotations


import pytest

from hamlet_ai.core.script_gen.character_voices import (
    LEGACY_DEFAULT_MAP,
    CharacterVoiceMap,
)


def test_load_missing_returns_legacy_defaults(tmp_path):
    cm = CharacterVoiceMap(tmp_path / "voices.json")
    loaded = cm.load()
    assert loaded["HAMLET"] == LEGACY_DEFAULT_MAP["HAMLET"]
    assert loaded["_default"] == LEGACY_DEFAULT_MAP["_default"]


def test_load_malformed_returns_defaults(tmp_path):
    path = tmp_path / "voices.json"
    path.write_text("{not valid")
    cm = CharacterVoiceMap(path)
    assert cm.load()["_default"] == LEGACY_DEFAULT_MAP["_default"]


def test_save_then_load_round_trip(tmp_path):
    path = tmp_path / "voices.json"
    cm = CharacterVoiceMap(path)
    cm.save({"HAMLET": "voice-A", "OPHELIA": "voice-B", "_default": "voice-D"})
    loaded = cm.load()
    assert loaded["HAMLET"] == "voice-A"
    assert loaded["OPHELIA"] == "voice-B"
    assert loaded["_default"] == "voice-D"


def test_save_merges_with_defaults_on_load(tmp_path):
    """User-saved mapping that drops a legacy default should still resolve."""
    path = tmp_path / "voices.json"
    cm = CharacterVoiceMap(path)
    cm.save({"NEW_CHAR": "voice-X", "_default": "voice-D"})
    loaded = cm.load()
    assert loaded["HAMLET"] == LEGACY_DEFAULT_MAP["HAMLET"]
    assert loaded["NEW_CHAR"] == "voice-X"


def test_resolve_uses_overrides_first(tmp_path):
    cm = CharacterVoiceMap(tmp_path / "voices.json")
    voice = cm.resolve("HAMLET", overrides={"HAMLET": "guest-voice"})
    assert voice == "guest-voice"


def test_resolve_falls_back_to_default_for_unknown_character(tmp_path):
    cm = CharacterVoiceMap(tmp_path / "voices.json")
    voice = cm.resolve("UNKNOWN_CHARACTER")
    assert voice == LEGACY_DEFAULT_MAP["_default"]


def test_save_is_atomic(tmp_path, monkeypatch):
    path = tmp_path / "voices.json"
    cm = CharacterVoiceMap(path)
    cm.save({"HAMLET": "v1", "_default": "vd"})
    before = path.read_text()

    def boom(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr("os.replace", boom)
    with pytest.raises(OSError):
        cm.save({"HAMLET": "v2", "_default": "vd"})
    assert path.read_text() == before
    assert list(tmp_path.glob(".voices-*")) == []
