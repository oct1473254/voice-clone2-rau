"""Backward-compatibility shim. The real pipeline now lives in
``hamlet_ai.core.voice_clone.pipeline``. Existing operators who run
``python voiceclone2.py`` still get the original end-to-end flow.

The original module re-exported a handful of functions and constants. We
preserve that surface (with thin adapters that pass an ``AppConfig``) so any
external import keeps working.
"""
from __future__ import annotations

import os
from typing import Callable

from dotenv import load_dotenv

from hamlet_ai.config import AppConfig, default_config, ensure_dirs
from hamlet_ai.core.voice_clone import pipeline as _pipeline

load_dotenv()


def _cfg() -> AppConfig:
    cfg = default_config()
    # Preserve the historical DRY_RUN module-level toggle so a caller who does
    # ``voiceclone2.DRY_RUN = True`` before invoking still sees the right behavior.
    cfg.dry_run = bool(globals().get("DRY_RUN", cfg.dry_run))
    return cfg


# --- Module-level constants kept for backward compatibility ----------------
API_KEY = os.environ.get("ELEVENLABS_API_KEY")
DRY_RUN = True
MODEL_ID = "eleven_multilingual_v2"
BASE_DIR = os.path.expanduser("~/Desktop/VOICE-CLONE")
SCRIPT_FILE = os.path.join(BASE_DIR, "SCRIPT", "clone.txt")
SAMPLE_DIR = os.path.join(BASE_DIR, "SAMPLE")
LINES_DIR = os.path.join(BASE_DIR, "LINES")
ARCHIVE_DIR = os.path.join(BASE_DIR, "ARCHIVE")
CLONE_POLL_INTERVAL = 5
CLONE_TIMEOUT = 120
VOICE_SETTINGS = {"stability": 0.3, "similarity_boost": 0.75, "speed": 1.2}


# --- Re-exports that match the original signatures -------------------------

def parse_script(script_file=SCRIPT_FILE, log_fn: Callable[[str], None] = print):
    from pathlib import Path
    return _pipeline.parse_script(Path(script_file), log_fn=log_fn)


def cleanup(log_fn: Callable[[str], None] = print):
    return _pipeline.cleanup(_cfg(), log_fn=log_fn)


def clone_voice(sample_dir=SAMPLE_DIR, log_fn: Callable[[str], None] = print):
    cfg = _cfg()
    # Honor the legacy ``sample_dir`` arg if a caller overrode it
    from pathlib import Path
    cfg.voice_clone.base_dir = Path(sample_dir).parent
    return _pipeline.clone_voice(cfg, log_fn=log_fn)


def wait_for_voice(voice_id, log_fn: Callable[[str], None] = print):
    return _pipeline.wait_for_voice(_cfg(), voice_id, log_fn=log_fn)


def synthesize(voice_id, text, filename, log_fn: Callable[[str], None] = print):
    return _pipeline.synthesize(_cfg(), voice_id, text, filename, log_fn=log_fn)


def generate_lines(voice_id, script_lines, log_fn: Callable[[str], None] = print):
    return _pipeline.generate_lines(_cfg(), voice_id, script_lines, log_fn=log_fn)


def main() -> None:
    from hamlet_ai.consent import new_consent

    cfg = _cfg()
    ensure_dirs(cfg)
    # Cloning now requires explicit consent. Prompt the operator before running.
    print(
        "This records the volunteer, uploads the sample to ElevenLabs, creates a "
        "voice clone, and generates lines in that voice."
    )
    answer = input("Has the volunteer consented? Type 'yes' to continue: ").strip().lower()
    if answer != "yes":
        raise SystemExit("❌ Consent not confirmed; aborting.")
    consent = new_consent("volunteer", "keep")
    _pipeline.run_show(cfg, consent=consent)


if __name__ == "__main__":
    main()
