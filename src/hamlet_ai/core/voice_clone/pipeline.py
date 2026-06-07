"""Voice-clone pipeline, extracted from the original ``voiceclone2.py``.

All functions take a ``cfg: AppConfig`` so paths and feature flags are explicit.
The legacy ``log_fn=print`` callback is preserved so callers (CLI, GUI workers)
can redirect progress messages.

Atomic writes (``.tmp`` + ``os.replace``) protect QLab from observing partial
files in ``LINES/`` mid-write.
"""
from __future__ import annotations

import os
import shutil
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Callable

from hamlet_ai.config import AppConfig
from hamlet_ai.core.audio.silent_audio import write_silent_for_extension
from hamlet_ai.core.elevenlabs import ElevenLabsClient


LogFn = Callable[[str], None]


def parse_script(script_file: Path, log_fn: LogFn = print) -> list[tuple[str, str]]:
    """Read clone.txt and return a list of (filename, text) tuples."""
    log_fn("📄 Parsing script file...")
    if not script_file.exists():
        raise FileNotFoundError(f"❌ Script file not found: {script_file}")

    content = script_file.read_text(encoding="utf-8")
    blocks = [b.strip() for b in content.split("\n\n") if b.strip()]

    lines: list[tuple[str, str]] = []
    for block in blocks:
        parts = block.split("\n", 1)
        if len(parts) == 2:
            filename = parts[0].strip()
            text = parts[1].strip()
            lines.append((filename, text))
            log_fn(f"   ✅ Loaded: {filename}")
        else:
            log_fn(f"   ⚠️ Skipping malformed block: {parts[0][:40]}")

    log_fn(f"📄 Script parsed: {len(lines)} lines ready.")
    return lines


def cleanup(cfg: AppConfig, log_fn: LogFn = print) -> Path | None:
    """Archive previous LINES and SAMPLE files. Returns the archive subfolder, or None."""
    log_fn("🗂️  Running cleanup...")

    lines_dir = cfg.voice_clone.lines_dir
    sample_dir = cfg.voice_clone.sample_dir
    archive_dir = cfg.voice_clone.archive_dir

    if not lines_dir.is_dir():
        log_fn("🗂️  LINES/ does not exist, nothing to archive.")
        return None

    lines_files = [f for f in lines_dir.iterdir() if not f.name.startswith(".") and f.is_file()]
    if not lines_files:
        log_fn("🗂️  LINES/ is empty, nothing to archive.")
        return None

    oldest = min(lines_files, key=lambda f: f.stat().st_mtime)
    timestamp = time.strftime("%Y%m%d_%H%M%S", time.localtime(oldest.stat().st_mtime))
    archive_subfolder = archive_dir / timestamp
    archive_subfolder.mkdir(parents=True, exist_ok=True)
    log_fn(f"🗂️  Archiving to: ARCHIVE/{timestamp}/")

    for f in lines_files:
        try:
            shutil.move(str(f), str(archive_subfolder / f.name))
            log_fn(f"   → Moved from LINES/: {f.name}")
        except OSError as e:
            log_fn(f"   ⚠️ Could not move {f.name} from LINES/: {e}")

    if sample_dir.is_dir():
        sample_files = [f for f in sample_dir.iterdir() if not f.name.startswith(".") and f.is_file()]
        if not sample_files:
            log_fn("🗂️  SAMPLE/ is empty, skipping.")
        else:
            for f in sample_files:
                try:
                    shutil.move(str(f), str(archive_subfolder / f.name))
                    log_fn(f"   → Moved from SAMPLE/: {f.name}")
                except OSError as e:
                    log_fn(f"   ⚠️ Could not move {f.name} from SAMPLE/: {e}")

    log_fn("🗂️  Cleanup complete.")
    return archive_subfolder


def clone_voice(
    cfg: AppConfig,
    log_fn: LogFn = print,
    client: ElevenLabsClient | None = None,
) -> str:
    """Upload volunteer audio from SAMPLE/ to ElevenLabs IVC and return a voice_id.

    ``client`` is injectable for tests; in production it's built from ``cfg.elevenlabs_api_key``.
    """
    log_fn("🎤 Starting voice clone...")
    sample_dir = cfg.voice_clone.sample_dir

    if not sample_dir.is_dir():
        raise FileNotFoundError("❌ No audio file found in SAMPLE/")
    audio_files = sorted(
        f for f in sample_dir.iterdir() if not f.name.startswith(".") and f.is_file()
    )
    if not audio_files:
        raise FileNotFoundError("❌ No audio file found in SAMPLE/")
    if len(audio_files) > 1:
        log_fn(f"   ⚠️ Multiple files in SAMPLE/, using first: {audio_files[0].name}")

    audio_path = audio_files[0]
    log_fn(f"   📁 Using: {audio_path.name}")

    if cfg.dry_run:
        log_fn("   🧪 DRY RUN — skipping API call, returning mock voice_id.")
        time.sleep(0.01)
        return "dry_run_voice_id_12345"

    if client is None:
        if not cfg.elevenlabs_api_key:
            raise RuntimeError("ELEVENLABS_API_KEY not set; cannot clone voice.")
        client = ElevenLabsClient(api_key=cfg.elevenlabs_api_key)

    voice_id = client.clone_voice(
        audio_path=str(audio_path), audio_filename=audio_path.name
    )
    log_fn(f"   ✅ Clone created. Voice ID: {voice_id}")
    return voice_id


def wait_for_voice(
    cfg: AppConfig,
    voice_id: str,
    log_fn: LogFn = print,
    sleep_fn: Callable[[float], None] = time.sleep,
    client: ElevenLabsClient | None = None,
) -> str:
    """Poll until the cloned voice is confirmed ready. ``sleep_fn`` is injectable for tests."""
    log_fn("⏳ Waiting for voice to be ready...")

    if cfg.dry_run:
        log_fn("   🧪 DRY RUN — skipping poll, voice assumed ready.")
        return voice_id

    if client is None:
        if not cfg.elevenlabs_api_key:
            raise RuntimeError("ELEVENLABS_API_KEY not set; cannot poll voice.")
        client = ElevenLabsClient(api_key=cfg.elevenlabs_api_key)

    elapsed = 0.0
    while elapsed < cfg.voice_clone.clone_timeout:
        status = client.get_voice_status(voice_id)
        if status == 200:
            log_fn(f"   ✅ Voice ready after {elapsed:.0f}s.")
            return voice_id
        if status == 404:
            log_fn(f"   ⏳ Not ready yet... ({elapsed:.0f}s elapsed)")
            sleep_fn(cfg.voice_clone.clone_poll_interval)
            elapsed += cfg.voice_clone.clone_poll_interval
        else:
            raise RuntimeError(f"❌ Voice status check failed: HTTP {status}")

    raise TimeoutError(
        f"❌ Voice not ready after {cfg.voice_clone.clone_timeout}s. Aborting."
    )


def synthesize(
    cfg: AppConfig,
    voice_id: str,
    text: str,
    filename: str,
    log_fn: LogFn = print,
    client: ElevenLabsClient | None = None,
    output_dir: Path | None = None,
) -> Path:
    """Generate a single audio line and save atomically to LINES/.

    Returns the final path written. Atomic via tmp + os.replace so QLab cannot
    observe a half-written file even if it's polling LINES/ during a show.
    """
    target_dir = output_dir if output_dir is not None else cfg.voice_clone.lines_dir
    target_dir.mkdir(parents=True, exist_ok=True)
    final_path = target_dir / filename
    tmp_path = target_dir / f".{filename}.tmp"

    if cfg.dry_run:
        # Write a real playable silent audio file so QLab + in-app playback work.
        write_silent_for_extension(final_path)
        log_fn(f"   🧪 DRY RUN — wrote silent {final_path.suffix}: {filename}")
        return final_path

    if client is None:
        if not cfg.elevenlabs_api_key:
            raise RuntimeError("ELEVENLABS_API_KEY not set; cannot synthesize.")
        client = ElevenLabsClient(api_key=cfg.elevenlabs_api_key)

    audio = client.synthesize(
        voice_id=voice_id,
        text=text,
        model_id=cfg.voice_clone.model_id,
        voice_settings=cfg.voice_clone.voice_settings,
    )
    tmp_path.write_bytes(audio)
    os.replace(tmp_path, final_path)
    log_fn(f"   ✅ Saved: {filename}")
    return final_path


def generate_lines(
    cfg: AppConfig,
    voice_id: str,
    script_lines: list[tuple[str, str]],
    log_fn: LogFn = print,
    progress_fn: Callable[[int, int], None] | None = None,
    client: ElevenLabsClient | None = None,
) -> list[Path]:
    """Iterate parsed script lines and synthesize each one. Returns paths written."""
    total = len(script_lines)
    log_fn(f"🎙️  Generating {total} lines...")

    written: list[Path] = []
    for idx, (filename, text) in enumerate(script_lines, 1):
        log_fn(f"   [{idx}/{total}] {filename}")
        try:
            path = synthesize(cfg, voice_id, text, filename, log_fn=log_fn, client=client)
            written.append(path)
        except Exception as e:  # noqa: BLE001 — keep going on per-line failures, matches legacy behavior
            log_fn(f"   ❌ Error on {filename}: {e}")
        if progress_fn is not None:
            progress_fn(idx, total)

    log_fn("✅ All lines generated.")
    return written


def run_show(cfg: AppConfig, log_fn: LogFn = print) -> None:
    """Reproduce the original ``voiceclone2.main`` orchestration end-to-end."""
    log_fn("\n🎭 HAMLET.AI — VOICE CLONE SCRIPT")
    log_fn("=" * 40)
    log_fn("\n⚡ Starting concurrent tasks...")

    voice_id: str | None = None
    script_lines: list[tuple[str, str]] | None = None

    with ThreadPoolExecutor(max_workers=3) as executor:
        future_voice = executor.submit(clone_voice, cfg, log_fn)
        future_cleanup = executor.submit(cleanup, cfg, log_fn)
        future_script = executor.submit(parse_script, cfg.voice_clone.script_file, log_fn)

        for future in as_completed([future_voice, future_cleanup, future_script]):
            result = future.result()
            if future is future_voice:
                voice_id = result  # type: ignore[assignment]
            elif future is future_script:
                script_lines = result  # type: ignore[assignment]

    log_fn("\n🔍 Confirming voice status...")
    assert voice_id is not None
    voice_id = wait_for_voice(cfg, voice_id, log_fn=log_fn)

    assert script_lines is not None
    generate_lines(cfg, voice_id, script_lines, log_fn=log_fn)

    log_fn("\n🎭 Done. Files are in LINES/ and ready for QLab.")
    log_fn("=" * 40)
