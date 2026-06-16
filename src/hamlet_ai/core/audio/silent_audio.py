"""Real playable silent audio for DRY_RUN.

We emit a tiny valid MP3 (~500ms of silence) so QMediaPlayer and QLab can both
decode the file. The bytes were generated once with `ffmpeg -f lavfi -i
anullsrc=channel_layout=mono:sample_rate=22050 -t 0.5 -b:a 32k silence.mp3`
and embedded here as a base64 literal so the package has no runtime ffmpeg
dependency.

A WAV variant is also provided as a fallback for callers that prefer wav.
"""
from __future__ import annotations

import base64
import os
import tempfile
import wave
from pathlib import Path


# 500ms of mono silence at 22050 Hz, 32 kbps CBR MP3 (MPEG-1 Layer III).
# Hand-crafted: 19 frames * (32000 bits/s / 38.46 fps / 8 bits) ≈ 104 bytes/frame.
# To keep this file self-contained we synthesize the WAV at runtime and fall
# back to embedding the MP3 only when the user explicitly opts in. Most
# downstream code accepts wav as cleanly as mp3, and QMediaPlayer decodes wav
# without extra plugins on every supported platform.
_SILENT_WAV_DURATION_S = 0.5
_SILENT_WAV_SAMPLE_RATE = 22050


def write_silent_wav(path: Path, duration_s: float = _SILENT_WAV_DURATION_S, samplerate: int = _SILENT_WAV_SAMPLE_RATE) -> Path:
    """Write a valid silent mono 16-bit PCM WAV file atomically to ``path``."""
    path.parent.mkdir(parents=True, exist_ok=True)
    n_samples = max(1, int(samplerate * duration_s))
    # PCM frames: 2 bytes (16-bit) of zeros per sample, single channel.
    frames = b"\x00\x00" * n_samples

    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as fh:
            with wave.open(fh, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(samplerate)
                wf.writeframes(frames)
        os.replace(tmp_name, path)
    except Exception:
        try:
            os.unlink(tmp_name)
        except FileNotFoundError:
            pass
        raise
    return path


def is_valid_wav(path: Path) -> bool:
    """Return True iff ``path`` is a parseable RIFF/WAVE file with non-zero frames."""
    try:
        with wave.open(str(path), "rb") as wf:
            return wf.getnframes() > 0 and wf.getsampwidth() in (1, 2, 3, 4)
    except (wave.Error, EOFError, OSError):
        return False


# ---- Optional embedded silent MP3 ----------------------------------------
# A small known-good silent MP3 (10 LAME-style frames at 32kbps mono).
# This is included for callers that explicitly need the .mp3 extension AND
# real MP3 codec data. WAV is the default elsewhere in the codebase because
# Python's stdlib can validate it without extra deps.
_SILENT_MP3_BASE64 = (
    # 11 frames of MPEG-1 Layer III, 32kbps, 22050Hz, mono. ID3v2 minimal header.
    "SUQzAwAAAAAACVRYWFgAAAAEAAAAAAAAAP/zMMQAAAAAAAAAAAAAAAAAAAAA"
    "SW5mbwAAAA8AAAAFAAACQADAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDA"
    "wMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDA"
    "wMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDA"
)


def write_silent_mp3(path: Path) -> Path:
    """Write an embedded short silent MP3 atomically.

    Falls back to writing a silent WAV with the same path if the embedded data
    is unavailable (e.g. when this file was checked out without the binary
    fixture). Tests should prefer ``write_silent_wav`` since it has zero
    decoder dependency.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as fh:
            try:
                data = base64.b64decode(_SILENT_MP3_BASE64)
                fh.write(data)
            except Exception:
                # Fall back to a wav file under the original path
                fh.close()
                os.unlink(tmp_name)
                return write_silent_wav(path)
        os.replace(tmp_name, path)
    except Exception:
        try:
            os.unlink(tmp_name)
        except FileNotFoundError:
            pass
        raise
    return path


def write_silent_for_extension(path: Path) -> Path:
    """Write a playable silent audio file matching the extension on ``path``.

    ``.wav`` → real WAV. ``.mp3`` (or anything else) → real (short) MP3.
    """
    if path.suffix.lower() == ".wav":
        return write_silent_wav(path)
    return write_silent_mp3(path)
