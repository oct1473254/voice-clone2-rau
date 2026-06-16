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
from pathlib import Path
from typing import Callable

from hamlet_ai.config import AppConfig
from hamlet_ai.consent import ConsentRecord, require_consent
from hamlet_ai.core.audio.silent_audio import write_silent_for_extension
from hamlet_ai.core.elevenlabs import ElevenLabsClient
from hamlet_ai.core.voice_clone.runs import RunFolder
from hamlet_ai.core.voice_clone.voice_library import VoiceEntry, VoiceLibrary


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
    sample_dir: Path | None = None,
) -> str:
    """Upload volunteer audio to ElevenLabs IVC and return a voice_id.

    Reads from ``sample_dir`` if given (the safe per-run path), else from the
    legacy ``cfg.voice_clone.sample_dir``. ``client`` is injectable for tests;
    in production it's built from ``cfg.elevenlabs_api_key``.
    """
    log_fn("🎤 Starting voice clone...")
    sample_dir = sample_dir if sample_dir is not None else cfg.voice_clone.sample_dir

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
        client = ElevenLabsClient(
            api_key=cfg.elevenlabs_api_key, timeout=cfg.voice_clone.api_timeout_seconds
        )

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
        client = ElevenLabsClient(
            api_key=cfg.elevenlabs_api_key, timeout=cfg.voice_clone.api_timeout_seconds
        )

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

    if cfg.dry_run:
        # Write a real playable silent audio file so QLab + in-app playback work.
        write_silent_for_extension(final_path)
        log_fn(f"   🧪 DRY RUN — wrote silent {final_path.suffix}: {filename}")
        return final_path

    if client is None:
        if not cfg.elevenlabs_api_key:
            raise RuntimeError("ELEVENLABS_API_KEY not set; cannot synthesize.")
        client = ElevenLabsClient(
            api_key=cfg.elevenlabs_api_key, timeout=cfg.voice_clone.api_timeout_seconds
        )

    audio = client.synthesize(
        voice_id=voice_id,
        text=text,
        model_id=cfg.voice_clone.model_id,
        voice_settings=cfg.voice_clone.voice_settings,
    )
    # Atomic write with tmp cleanup-on-failure so QLab never sees a partial file.
    from hamlet_ai.core.elevenlabs import write_audio_atomic

    write_audio_atomic(final_path, audio)
    log_fn(f"   ✅ Saved: {filename}")
    return final_path


def generate_lines(
    cfg: AppConfig,
    voice_id: str,
    script_lines: list[tuple[str, str]],
    log_fn: LogFn = print,
    progress_fn: Callable[[int, int], None] | None = None,
    client: ElevenLabsClient | None = None,
    output_dir: Path | None = None,
) -> list[Path]:
    """Iterate parsed script lines and synthesize each one. Returns paths written."""
    total = len(script_lines)
    log_fn(f"🎙️  Generating {total} lines...")

    written: list[Path] = []
    for idx, (filename, text) in enumerate(script_lines, 1):
        log_fn(f"   [{idx}/{total}] {filename}")
        try:
            path = synthesize(
                cfg, voice_id, text, filename, log_fn=log_fn, client=client, output_dir=output_dir
            )
            written.append(path)
        except Exception as e:  # noqa: BLE001 — keep going on per-line failures, matches legacy behavior
            log_fn(f"   ❌ Error on {filename}: {e}")
        if progress_fn is not None:
            progress_fn(idx, total)

    log_fn("✅ All lines generated.")
    return written


def archive_lines(cfg: AppConfig, log_fn: LogFn = print) -> Path | None:
    """Archive the *current* ``LINES/`` content into ``ARCHIVE/{prev_ts}/``.

    Unlike the legacy ``cleanup`` this never touches ``SAMPLE/`` — the new flow
    keeps the volunteer sample where it is. Returns the archive subfolder, or
    ``None`` if there was nothing to archive.
    """
    lines_dir = cfg.voice_clone.lines_dir
    archive_dir = cfg.voice_clone.archive_dir
    if not lines_dir.is_dir():
        return None
    lines_files = [f for f in lines_dir.iterdir() if not f.name.startswith(".") and f.is_file()]
    if not lines_files:
        return None

    oldest = min(lines_files, key=lambda f: f.stat().st_mtime)
    timestamp = time.strftime("%Y%m%d_%H%M%S", time.localtime(oldest.stat().st_mtime))
    archive_subfolder = archive_dir / timestamp
    suffix = 1
    while archive_subfolder.exists():
        archive_subfolder = archive_dir / f"{timestamp}_{suffix}"
        suffix += 1
    archive_subfolder.mkdir(parents=True, exist_ok=True)
    log_fn(f"🗂️  Archiving previous LINES/ → ARCHIVE/{archive_subfolder.name}/")
    for f in lines_files:
        shutil.move(str(f), str(archive_subfolder / f.name))
    return archive_subfolder


def restore_last_good(
    cfg: AppConfig,
    archive_name: str | None = None,
    log_fn: LogFn = print,
) -> list[Path]:
    """Copy an archived run's files back into ``LINES/`` — the show-night rescue.

    ``archive_name`` selects a specific ``ARCHIVE/{ts}/`` subfolder; if omitted,
    the most recent archive is used. Copies (does not move) so the archive stays
    intact, one file at a time via atomic ``os.replace``.
    """
    archive_dir = cfg.voice_clone.archive_dir
    lines_dir = cfg.voice_clone.lines_dir
    if not archive_dir.is_dir():
        raise FileNotFoundError("❌ No ARCHIVE/ directory to restore from.")

    subfolders = sorted(
        (d for d in archive_dir.iterdir() if d.is_dir()),
        key=lambda d: d.name,
        reverse=True,
    )
    if not subfolders:
        raise FileNotFoundError("❌ No archived runs to restore.")

    if archive_name is not None:
        chosen = archive_dir / archive_name
        if not chosen.is_dir():
            raise FileNotFoundError(f"❌ Archive not found: {archive_name}")
    else:
        chosen = subfolders[0]

    lines_dir.mkdir(parents=True, exist_ok=True)
    log_fn(f"♻️  Restoring LINES/ from ARCHIVE/{chosen.name}/")
    restored: list[Path] = []
    for src in sorted(f for f in chosen.iterdir() if f.is_file() and not f.name.startswith(".")):
        final_path = lines_dir / src.name
        tmp_path = lines_dir / f".{src.name}.tmp"
        shutil.copy2(src, tmp_path)
        os.replace(tmp_path, final_path)
        restored.append(final_path)
        log_fn(f"   ♻️  {src.name}")
    return restored


def run_show(
    cfg: AppConfig,
    consent: "ConsentRecord | None" = None,
    log_fn: LogFn = print,
    client: ElevenLabsClient | None = None,
    now: float | None = None,
    clock: Callable[[], float] = time.monotonic,
) -> RunFolder:
    """Run one voice-clone session safely and sequentially.

    Flow (no concurrent cleanup-during-clone race):
      1. Require consent.
      2. Create a fresh RunFolder.
      3. Copy the supplied sample into the run folder.
      4. Sequentially clone → wait → write metadata → parse → generate into the
         run's ``generated_lines/``.
      5. On success archive the previous ``LINES/`` and swap the run's lines in.
      6. On failure ``LINES/`` is left untouched.

    Returns the :class:`RunFolder` for the session.
    """
    consent = require_consent(consent)

    log_fn("\n🎭 HAMLET.AI — VOICE CLONE SCRIPT")
    log_fn("=" * 40)

    t_start = clock()
    run = RunFolder.create_for_now(cfg, now=now)
    run.append_log("run started")
    log_fn(f"📂 Run folder: {run.root}")

    # Copy the volunteer sample into the run folder (never move it out of SAMPLE/).
    sample_files = sorted(
        f for f in cfg.voice_clone.sample_dir.iterdir()
        if f.is_file() and not f.name.startswith(".")
    ) if cfg.voice_clone.sample_dir.is_dir() else []
    if not sample_files:
        raise FileNotFoundError("❌ No audio file found in SAMPLE/")
    run.copy_sample_in(sample_files[0])
    log_fn(f"   📎 Copied sample into run: {sample_files[0].name}")

    # Sequential pipeline — clone reads from the run's own sample copy.
    voice_id = clone_voice(cfg, log_fn=log_fn, client=client, sample_dir=run.sample_dir)
    voice_id = wait_for_voice(cfg, voice_id, log_fn=log_fn, client=client)
    t_clone_ready = clock()

    run.write_metadata(
        {
            "voice_id": voice_id,
            "consent": consent.to_dict(),
            "recording_target_seconds": cfg.voice_clone.recording_target_seconds,
            "model_id": cfg.voice_clone.model_id,
            "retention_policy": consent.retention_policy,
            "dry_run": cfg.dry_run,
        }
    )
    run.append_log(f"voice_id={voice_id}")

    script_lines = parse_script(cfg.voice_clone.script_file, log_fn=log_fn)
    generate_lines(
        cfg,
        voice_id,
        script_lines,
        log_fn=log_fn,
        client=client,
        output_dir=run.generated_lines_dir,
    )

    # Success: archive the previous LINES/ then swap this run's lines in.
    archive_lines(cfg, log_fn=log_fn)
    cfg.voice_clone.lines_dir.mkdir(parents=True, exist_ok=True)
    generated = sorted(
        f for f in run.generated_lines_dir.iterdir()
        if f.is_file() and not f.name.startswith(".")
    )
    for src in generated:
        os.replace(src, cfg.voice_clone.lines_dir / src.name)
    log_fn(f"   📤 Swapped {len(generated)} files into LINES/")

    # Record the clone in the persistent library.
    _record_in_library(cfg, voice_id, consent, run)

    # Performance budget (Step 16): time each phase and flag overruns so the GUI
    # can offer fallbacks (stock voice / restore last good).
    t_done = clock()
    target = cfg.voice_clone.target_total_seconds
    timings = {
        "clone_ready_seconds": round(t_clone_ready - t_start, 2),
        "generation_seconds": round(t_done - t_clone_ready, 2),
        "total_seconds": round(t_done - t_start, 2),
        "target_total_seconds": target,
        "within_budget": (t_done - t_start) <= target,
    }
    run.timings = timings
    run.update_metadata({"timings": timings})
    run.append_log(
        "timings: clone_ready={clone_ready_seconds}s "
        "generation={generation_seconds}s total={total_seconds}s "
        "target={target_total_seconds}s within_budget={within_budget}".format(**timings)
    )
    status = "within" if timings["within_budget"] else "OVER"
    log_fn(
        f"⏱️  Total {timings['total_seconds']}s "
        f"(clone {timings['clone_ready_seconds']}s + generate "
        f"{timings['generation_seconds']}s) — {status} the {target}s budget."
    )

    run.append_log("run complete")
    log_fn("\n🎭 Done. Files are in LINES/ and ready for QLab.")
    log_fn("=" * 40)
    return run


def _record_in_library(
    cfg: AppConfig,
    voice_id: str,
    consent: "ConsentRecord",
    run: RunFolder,
) -> None:
    """Append the new clone to the VoiceLibrary with its consent metadata."""
    sample_files = sorted(
        f for f in run.sample_dir.iterdir() if f.is_file() and not f.name.startswith(".")
    )
    sample_path = sample_files[0] if sample_files else run.sample_dir
    library = VoiceLibrary(cfg.voice_clone.voice_library_path)
    # Ephemeral show mode forces every new clone to be deleted at end of session.
    retention_policy = (
        "ephemeral" if cfg.retention.ephemeral_show_mode else consent.retention_policy
    )
    entry = VoiceEntry.new(
        voice_id=voice_id,
        label=consent.volunteer_label,
        sample_path=str(sample_path),
        sample_filename=sample_path.name,
        consent_confirmed=consent.confirmed_by_operator,
        consent_timestamp=consent.confirmed_at,
        retention_policy=retention_policy,
        provider_metadata={"model_id": cfg.voice_clone.model_id, "run": run.root.name},
    )
    library.add(entry)
