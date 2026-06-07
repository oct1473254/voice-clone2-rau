"""Single source of truth for paths, model IDs, voice settings, and feature flags.

``AppConfig`` collects every knob that the legacy ``voiceclone2.py`` and
``Hamlet-gen5.py`` modules read from module globals. ``default_config`` loads
overrides from ``~/.config/hamlet-ai/settings.json`` if present and falls back
to the hardcoded defaults that match today's behavior.

Importing this module has no side effects: it never creates directories,
reads ``.env``, or raises on missing keys. Use ``ensure_dirs(cfg)`` to lay out
workspaces and ``load_env`` to populate the keys on demand.
"""
from __future__ import annotations

import json
import os
import shutil
import tempfile
from dataclasses import asdict, dataclass, field, fields, replace
from pathlib import Path
from typing import Any


SETTINGS_PATH_DEFAULT = Path.home() / ".config" / "hamlet-ai" / "settings.json"


@dataclass
class VoiceCloneSettings:
    base_dir: Path = Path.home() / "Desktop" / "VOICE-CLONE"
    recording_target_seconds: float = 90.0
    recording_samplerate: int = 48000
    clone_poll_interval: float = 5.0
    clone_timeout: float = 120.0
    model_id: str = "eleven_v3"
    voice_settings: dict[str, float] = field(
        default_factory=lambda: {
            "stability": 0.3,
            "similarity_boost": 0.75,
            "speed": 1.2,
        }
    )

    @property
    def script_file(self) -> Path:
        return self.base_dir / "SCRIPT" / "clone.txt"

    @property
    def sample_dir(self) -> Path:
        return self.base_dir / "SAMPLE"

    @property
    def lines_dir(self) -> Path:
        return self.base_dir / "LINES"

    @property
    def archive_dir(self) -> Path:
        return self.base_dir / "ARCHIVE"

    @property
    def runs_dir(self) -> Path:
        return self.base_dir / "RUNS"

    @property
    def adhoc_dir(self) -> Path:
        return self.base_dir / "ADHOC"

    @property
    def voice_library_path(self) -> Path:
        return self.base_dir / "voice_library.json"


@dataclass
class ScriptGenSettings:
    base_dir: Path = Path.home() / "Desktop" / "LLM-H"
    workspace_dir: Path = Path.home() / ".cache" / "hamlet-ai" / "script_gen_workspace"
    default_provider: str = "anthropic"
    translation_provider: str | None = None  # None → reuse default_provider
    models: dict[str, str] = field(
        default_factory=lambda: {
            "anthropic": "claude-sonnet-4-6",
            "openai": "gpt-4o",
            "ollama": "llama3.1",
        }
    )
    tts_model_id: str = "eleven_v3"
    tts_voice_settings: dict[str, float] = field(
        default_factory=lambda: {
            "stability": 0.5,
            "similarity_boost": 0.5,
        }
    )

    @property
    def character_voices_path(self) -> Path:
        return self.base_dir / "voices.json"


@dataclass
class AppConfig:
    voice_clone: VoiceCloneSettings = field(default_factory=VoiceCloneSettings)
    script_gen: ScriptGenSettings = field(default_factory=ScriptGenSettings)
    dry_run: bool = True
    elevenlabs_api_key: str | None = None
    anthropic_api_key: str | None = None
    openai_api_key: str | None = None


# ---------- serialization helpers -----------------------------------------

def _to_dict(cfg: AppConfig) -> dict[str, Any]:
    """Serialize an AppConfig to JSON-safe primitives (Paths → strings)."""

    def coerce(value: Any) -> Any:
        if isinstance(value, Path):
            return str(value)
        if isinstance(value, dict):
            return {k: coerce(v) for k, v in value.items()}
        if isinstance(value, list):
            return [coerce(v) for v in value]
        return value

    payload: dict[str, Any] = {}
    for f in fields(cfg):
        value = getattr(cfg, f.name)
        if isinstance(value, (VoiceCloneSettings, ScriptGenSettings)):
            payload[f.name] = {
                sub.name: coerce(getattr(value, sub.name)) for sub in fields(value)
            }
        else:
            payload[f.name] = coerce(value)
    return payload


def _apply_overrides(cfg: AppConfig, data: dict[str, Any]) -> AppConfig:
    """Return a new AppConfig with fields overridden by ``data``."""

    def coerce_path(field_name: str, current: Any, raw: Any) -> Any:
        if isinstance(current, Path):
            return Path(raw).expanduser() if raw is not None else current
        return raw

    voice_clone_data = data.get("voice_clone", {}) or {}
    vc_overrides: dict[str, Any] = {}
    for f in fields(cfg.voice_clone):
        if f.name in voice_clone_data:
            vc_overrides[f.name] = coerce_path(
                f.name, getattr(cfg.voice_clone, f.name), voice_clone_data[f.name]
            )
    new_voice = replace(cfg.voice_clone, **vc_overrides) if vc_overrides else cfg.voice_clone

    script_gen_data = data.get("script_gen", {}) or {}
    sg_overrides: dict[str, Any] = {}
    for f in fields(cfg.script_gen):
        if f.name in script_gen_data:
            sg_overrides[f.name] = coerce_path(
                f.name, getattr(cfg.script_gen, f.name), script_gen_data[f.name]
            )
    new_script = replace(cfg.script_gen, **sg_overrides) if sg_overrides else cfg.script_gen

    top_overrides: dict[str, Any] = {}
    for f in fields(cfg):
        if f.name in {"voice_clone", "script_gen"}:
            continue
        if f.name in data:
            top_overrides[f.name] = data[f.name]

    return replace(cfg, voice_clone=new_voice, script_gen=new_script, **top_overrides)


# ---------- public API -----------------------------------------------------

def default_config(settings_path: Path | None = None) -> AppConfig:
    """Build the default AppConfig, applying overrides from ``settings_path`` if it exists."""
    cfg = AppConfig()
    cfg = _apply_env_keys(cfg)
    path = settings_path if settings_path is not None else SETTINGS_PATH_DEFAULT
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return cfg
        if isinstance(data, dict):
            cfg = _apply_overrides(cfg, data)
    return cfg


def _apply_env_keys(cfg: AppConfig) -> AppConfig:
    """Populate API keys from environment variables if present."""
    return replace(
        cfg,
        elevenlabs_api_key=os.environ.get("ELEVENLABS_API_KEY") or cfg.elevenlabs_api_key,
        anthropic_api_key=os.environ.get("ANTHROPIC_API_KEY") or cfg.anthropic_api_key,
        openai_api_key=os.environ.get("OPENAI_API_KEY") or cfg.openai_api_key,
    )


def save_config(cfg: AppConfig, settings_path: Path | None = None) -> Path:
    """Atomically write the (non-secret) parts of cfg to disk. Returns the path written."""
    path = settings_path if settings_path is not None else SETTINGS_PATH_DEFAULT
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _to_dict(cfg)
    # Never persist API keys to disk — they live in .env / environment.
    for key in ("elevenlabs_api_key", "anthropic_api_key", "openai_api_key"):
        payload.pop(key, None)

    fd, tmp_name = tempfile.mkstemp(prefix=".settings-", suffix=".json", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2, sort_keys=True)
        os.replace(tmp_name, path)
    except Exception:
        try:
            os.unlink(tmp_name)
        except FileNotFoundError:
            pass
        raise
    return path


def ensure_dirs(cfg: AppConfig) -> None:
    """Create workspace directories. Idempotent."""
    for directory in (
        cfg.voice_clone.sample_dir,
        cfg.voice_clone.lines_dir,
        cfg.voice_clone.archive_dir,
        cfg.voice_clone.runs_dir,
        cfg.voice_clone.adhoc_dir,
        cfg.voice_clone.script_file.parent,
        cfg.script_gen.base_dir,
        cfg.script_gen.workspace_dir,
    ):
        directory.mkdir(parents=True, exist_ok=True)
