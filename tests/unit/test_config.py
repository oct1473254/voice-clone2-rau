"""Step 2: AppConfig defaults, overrides, persistence, and ensure_dirs."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from hamlet_ai.config import (
    AppConfig,
    ProviderHealth,
    RetentionSettings,
    ScriptGenSettings,
    VoiceCloneSettings,
    default_config,
    ensure_dirs,
    save_config,
)


def test_default_config_paths_match_legacy_behavior(monkeypatch):
    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    cfg = default_config(settings_path=Path("/no/such/path.json"))
    home = Path.home()
    assert cfg.voice_clone.base_dir == home / "Desktop" / "VOICE-CLONE"
    assert cfg.voice_clone.script_file == home / "Desktop" / "VOICE-CLONE" / "SCRIPT" / "clone.txt"
    assert cfg.voice_clone.sample_dir == home / "Desktop" / "VOICE-CLONE" / "SAMPLE"
    assert cfg.voice_clone.lines_dir == home / "Desktop" / "VOICE-CLONE" / "LINES"
    assert cfg.voice_clone.archive_dir == home / "Desktop" / "VOICE-CLONE" / "ARCHIVE"
    assert cfg.script_gen.base_dir == home / "Desktop" / "LLM-H"
    assert cfg.dry_run is True


def test_default_config_voice_settings_match_voiceclone2_globals():
    cfg = default_config(settings_path=Path("/no/such/path.json"))
    assert cfg.voice_clone.voice_settings == {
        "stability": 0.3,
        "similarity_boost": 0.75,
        "speed": 1.2,
    }
    assert cfg.voice_clone.clone_poll_interval == 5
    assert cfg.voice_clone.clone_timeout == 120
    assert cfg.voice_clone.model_id == "eleven_v3"


def test_default_config_script_gen_provider_defaults():
    cfg = default_config(settings_path=Path("/no/such/path.json"))
    assert cfg.script_gen.default_provider == "anthropic"
    assert cfg.script_gen.translation_provider is None
    assert cfg.script_gen.models == {
        "anthropic": "claude-sonnet-4-6",
        "openai": "gpt-4o",
        "ollama": "llama3.1",
    }


def test_default_config_reads_env_api_keys(monkeypatch):
    monkeypatch.setenv("ELEVENLABS_API_KEY", "el-xyz")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "an-xyz")
    monkeypatch.setenv("OPENAI_API_KEY", "op-xyz")
    cfg = default_config(settings_path=Path("/no/such/path.json"))
    assert cfg.elevenlabs_api_key == "el-xyz"
    assert cfg.anthropic_api_key == "an-xyz"
    assert cfg.openai_api_key == "op-xyz"


def test_default_config_applies_partial_overrides(tmp_path):
    settings = tmp_path / "settings.json"
    settings.write_text(
        json.dumps(
            {
                "dry_run": False,
                "voice_clone": {
                    "recording_target_seconds": 60.0,
                    "model_id": "eleven_flash_v2_5",
                },
                "script_gen": {
                    "default_provider": "openai",
                    "models": {
                        "anthropic": "claude-opus-4-7",
                        "openai": "gpt-4o-mini",
                        "ollama": "llama3.2",
                    },
                },
            }
        )
    )
    cfg = default_config(settings_path=settings)
    assert cfg.dry_run is False
    assert cfg.voice_clone.recording_target_seconds == 60.0
    assert cfg.voice_clone.model_id == "eleven_flash_v2_5"
    # untouched defaults remain
    assert cfg.voice_clone.voice_settings["stability"] == 0.3
    assert cfg.script_gen.default_provider == "openai"
    assert cfg.script_gen.models["openai"] == "gpt-4o-mini"


def test_default_config_ignores_malformed_settings_file(tmp_path):
    settings = tmp_path / "settings.json"
    settings.write_text("{not valid json")
    cfg = default_config(settings_path=settings)
    assert cfg.dry_run is True
    assert cfg.voice_clone.recording_target_seconds == 90.0


def test_save_then_load_round_trip(tmp_path, monkeypatch):
    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)
    settings = tmp_path / "settings.json"
    cfg = default_config(settings_path=Path("/no/such/path.json"))
    cfg.voice_clone.recording_target_seconds = 45.0
    cfg.script_gen.default_provider = "ollama"
    cfg.dry_run = False
    save_config(cfg, settings_path=settings)

    loaded = default_config(settings_path=settings)
    assert loaded.voice_clone.recording_target_seconds == 45.0
    assert loaded.script_gen.default_provider == "ollama"
    assert loaded.dry_run is False


def test_save_config_never_writes_api_keys(tmp_path):
    settings = tmp_path / "settings.json"
    cfg = AppConfig(elevenlabs_api_key="secret-el", anthropic_api_key="secret-an", openai_api_key="secret-op")
    save_config(cfg, settings_path=settings)
    raw = settings.read_text(encoding="utf-8")
    assert "secret-el" not in raw
    assert "secret-an" not in raw
    assert "secret-op" not in raw
    assert "elevenlabs_api_key" not in raw


def test_save_config_is_atomic(tmp_path, monkeypatch):
    """A failing write must not leave a half-written settings file."""
    settings = tmp_path / "settings.json"
    settings.write_text('{"dry_run": true}')
    original = settings.read_text()

    def boom(*args, **kwargs):
        raise OSError("simulated disk full")

    monkeypatch.setattr("os.replace", boom)
    cfg = AppConfig()
    cfg.dry_run = False
    with pytest.raises(OSError):
        save_config(cfg, settings_path=settings)
    assert settings.read_text() == original
    leftover = list(tmp_path.glob(".settings-*"))
    assert leftover == [], f"temp files leaked: {leftover}"


def test_ensure_dirs_idempotent(tmp_path):
    cfg = AppConfig(
        voice_clone=VoiceCloneSettings(base_dir=tmp_path / "vc"),
        script_gen=ScriptGenSettings(
            base_dir=tmp_path / "sg",
            workspace_dir=tmp_path / "sg" / "ws",
        ),
    )
    ensure_dirs(cfg)
    ensure_dirs(cfg)  # second call must not raise
    assert cfg.voice_clone.sample_dir.is_dir()
    assert cfg.voice_clone.lines_dir.is_dir()
    assert cfg.voice_clone.archive_dir.is_dir()
    assert cfg.voice_clone.adhoc_dir.is_dir()
    assert cfg.voice_clone.script_file.parent.is_dir()
    assert cfg.script_gen.base_dir.is_dir()
    assert cfg.script_gen.workspace_dir.is_dir()


def test_default_show_mode_and_retention_defaults():
    cfg = default_config(settings_path=Path("/no/such/path.json"))
    assert cfg.show_mode is False
    assert cfg.show_profile == "default"
    assert isinstance(cfg.retention, RetentionSettings)
    assert cfg.retention.ephemeral_show_mode is False
    assert cfg.retention.delete_after_show_ttl_hours == 24.0
    assert cfg.provider_health == {}


def test_show_mode_and_retention_round_trip(tmp_path, monkeypatch):
    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)
    settings = tmp_path / "settings.json"
    cfg = AppConfig()
    cfg.show_mode = True
    cfg.show_profile = "wember-night"
    cfg.retention.ephemeral_show_mode = True
    cfg.retention.sample_ttl_hours = 6.0
    cfg.provider_health = {
        "anthropic": ProviderHealth(status="ok", last_tested="2026-06-06T00:00:00+00:00", message="pong")
    }
    save_config(cfg, settings_path=settings)

    loaded = default_config(settings_path=settings)
    assert loaded.show_mode is True
    assert loaded.show_profile == "wember-night"
    assert isinstance(loaded.retention, RetentionSettings)
    assert loaded.retention.ephemeral_show_mode is True
    assert loaded.retention.sample_ttl_hours == 6.0
    assert isinstance(loaded.provider_health["anthropic"], ProviderHealth)
    assert loaded.provider_health["anthropic"].status == "ok"
    assert loaded.provider_health["anthropic"].message == "pong"


def test_overrides_ignore_unknown_retention_keys(tmp_path):
    settings = tmp_path / "settings.json"
    settings.write_text(
        json.dumps({"retention": {"sample_ttl_hours": 3.0, "bogus_key": 99}})
    )
    cfg = default_config(settings_path=settings)
    assert cfg.retention.sample_ttl_hours == 3.0
    assert not hasattr(cfg.retention, "bogus_key")


def test_importing_config_has_no_side_effects(tmp_path, monkeypatch):
    """Just importing the module must not create directories or call APIs."""
    monkeypatch.setenv("HOME", str(tmp_path))
    import importlib
    import hamlet_ai.config as mod

    importlib.reload(mod)
    # Nothing under tmp_path should have been created by import
    children = list(tmp_path.iterdir())
    assert children == [], f"import created files: {children}"
