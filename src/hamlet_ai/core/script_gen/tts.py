"""Script-gen TTS: synthesize a single split line to audio via ElevenLabs.

Writes audio atomically (``.tmp`` + ``os.replace``). In DRY_RUN, writes a
placeholder file the GUI can still preview as "exists" for state-tracking
purposes.
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Callable

from hamlet_ai.config import AppConfig
from hamlet_ai.core.elevenlabs import ElevenLabsClient


LogFn = Callable[[str], None]


def synthesize_line(
    cfg: AppConfig,
    text: str,
    voice_id: str,
    output_path: Path,
    log_fn: LogFn = print,
    client: ElevenLabsClient | None = None,
) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if cfg.dry_run:
        # Write a real, short, playable silent audio file (matching the output
        # extension) so QLab + the in-app player can decode DRY_RUN output.
        from hamlet_ai.core.audio.silent_audio import write_silent_for_extension

        write_silent_for_extension(output_path)
        log_fn(f"   🧪 DRY RUN — wrote silent {output_path.suffix}: {output_path.name}")
        return output_path

    if client is None:
        if not cfg.elevenlabs_api_key:
            raise RuntimeError("ELEVENLABS_API_KEY not set; cannot synthesize.")
        client = ElevenLabsClient(api_key=cfg.elevenlabs_api_key)

    audio = client.synthesize(
        voice_id=voice_id,
        text=text,
        model_id=cfg.script_gen.tts_model_id,
        voice_settings=cfg.script_gen.tts_voice_settings,
    )
    _atomic_write_bytes(output_path, audio)
    log_fn(f"   ✅ Saved: {output_path.name}")
    return output_path


def _atomic_write_bytes(path: Path, data: bytes) -> None:
    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
        os.replace(tmp_name, path)
    except Exception:
        try:
            os.unlink(tmp_name)
        except FileNotFoundError:
            pass
        raise
