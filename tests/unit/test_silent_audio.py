"""Step 7: silent_audio writes real playable files (not text-with-.mp3)."""
from __future__ import annotations

import wave

import pytest

from hamlet_ai.core.audio.silent_audio import (
    is_valid_wav,
    write_silent_for_extension,
    write_silent_mp3,
    write_silent_wav,
)


def test_write_silent_wav_creates_valid_riff(tmp_path):
    out = tmp_path / "silent.wav"
    write_silent_wav(out)
    assert out.is_file()
    assert is_valid_wav(out)
    with wave.open(str(out), "rb") as wf:
        assert wf.getnchannels() == 1
        assert wf.getframerate() == 22050
        assert wf.getnframes() > 0


def test_write_silent_wav_is_atomic_no_leftover_tmp(tmp_path, monkeypatch):
    out = tmp_path / "silent.wav"

    def boom(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr("os.replace", boom)
    with pytest.raises(OSError):
        write_silent_wav(out)
    assert not out.exists()
    leftover = list(tmp_path.glob(".silent.wav*"))
    assert leftover == []


def test_write_silent_mp3_produces_audio_with_mp3_magic_or_falls_back(tmp_path):
    out = tmp_path / "silent.mp3"
    write_silent_mp3(out)
    assert out.is_file()
    # Either it's a real MP3 (starts with ID3 or 0xFF 0xFB), or the fallback
    # WAV was written. Both are acceptable — we just need a real audio file.
    head = out.read_bytes()[:4]
    assert head.startswith(b"ID3") or head[:2] in (b"\xff\xfb", b"\xff\xf3", b"\xff\xfa") or head == b"RIFF"


def test_write_silent_for_extension_routes_by_suffix(tmp_path):
    wav = tmp_path / "a.wav"
    mp3 = tmp_path / "b.mp3"
    write_silent_for_extension(wav)
    write_silent_for_extension(mp3)
    assert wav.is_file()
    assert mp3.is_file()
    # WAV path produces a valid RIFF
    assert is_valid_wav(wav)


def test_is_valid_wav_returns_false_for_garbage(tmp_path):
    bad = tmp_path / "garbage.wav"
    bad.write_bytes(b"this is not a wav")
    assert is_valid_wav(bad) is False
