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
import tempfile
from dataclasses import dataclass, field, fields, is_dataclass, replace
from pathlib import Path
from typing import Any


SETTINGS_PATH_DEFAULT = Path.home() / ".config" / "hamlet-ai" / "settings.json"


@dataclass
class RetentionSettings:
    """How long cloned-voice artifacts live before the sweep removes them.

    ``ephemeral_show_mode`` is the global default-ephemeral flag: when True,
    every new clone is created with ``retention_policy="ephemeral"`` and is
    deleted (local + remote) at end of session.
    """

    sample_ttl_hours: float = 24.0
    archive_ttl_hours: float = 720.0  # 30 days
    generated_ttl_hours: float = 24.0
    delete_after_show_ttl_hours: float = 24.0
    ephemeral_show_mode: bool = False


@dataclass
class ProviderHealth:
    """Last-known connectivity for an LLM provider (set by ``test_connection``)."""

    status: str = "unknown"  # "ok" | "failed" | "unknown"
    last_tested: str | None = None  # ISO 8601 UTC
    message: str = ""


@dataclass
class VoiceCloneSettings:
    base_dir: Path = Path.home() / "Desktop" / "VOICE-CLONE"
    recording_target_seconds: float = 90.0
    recording_samplerate: int = 48000
    clone_poll_interval: float = 5.0
    clone_timeout: float = 120.0
    api_timeout_seconds: float = 30.0
    # Performance budget (Step 16): the README promises a clone-to-QLab turnaround
    # under two minutes. run_show times itself against this and flags overruns so
    # the GUI can offer fallback (stock voice / restore last good).
    target_total_seconds: float = 120.0
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
    show_mode: bool = False
    show_profile: str = "default"
    retention: RetentionSettings = field(default_factory=RetentionSettings)
    provider_health: dict[str, ProviderHealth] = field(default_factory=dict)
    elevenlabs_api_key: str | None = None
    anthropic_api_key: str | None = None
    openai_api_key: str | None = None


# ---------- serialization helpers -----------------------------------------

def _coerce(value: Any) -> Any:
    """Recursively convert a value to JSON-safe primitives.

    Handles Paths, nested dataclasses (settings groups, RetentionSettings,
    ProviderHealth), dicts (incl. dict-of-dataclass like ``provider_health``),
    and lists.
    """
    if isinstance(value, Path):
        return str(value)
    if is_dataclass(value) and not isinstance(value, type):
        return {f.name: _coerce(getattr(value, f.name)) for f in fields(value)}
    if isinstance(value, dict):
        return {k: _coerce(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_coerce(v) for v in value]
    return value


def _to_dict(cfg: AppConfig) -> dict[str, Any]:
    """Serialize an AppConfig to JSON-safe primitives (Paths → strings)."""
    return {f.name: _coerce(getattr(cfg, f.name)) for f in fields(cfg)}


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

    # Fields that need bespoke reconstruction into their dataclass types.
    structured = {"voice_clone", "script_gen", "retention", "provider_health"}

    top_overrides: dict[str, Any] = {}
    for f in fields(cfg):
        if f.name in structured:
            continue
        if f.name in data:
            top_overrides[f.name] = data[f.name]

    if "retention" in data and isinstance(data["retention"], dict):
        top_overrides["retention"] = _build_dataclass(
            RetentionSettings, data["retention"], cfg.retention
        )

    if "provider_health" in data and isinstance(data["provider_health"], dict):
        health: dict[str, ProviderHealth] = {}
        for name, raw in data["provider_health"].items():
            if isinstance(raw, dict):
                health[name] = _build_dataclass(ProviderHealth, raw, ProviderHealth())
        top_overrides["provider_health"] = health

    return replace(cfg, voice_clone=new_voice, script_gen=new_script, **top_overrides)


def _build_dataclass(cls: type, data: dict[str, Any], default: Any) -> Any:
    """Construct ``cls`` from ``data``, ignoring unknown keys and filling the
    rest from ``default``."""
    known = {f.name for f in fields(cls)}
    overrides = {k: v for k, v in data.items() if k in known}
    return replace(default, **overrides)


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
