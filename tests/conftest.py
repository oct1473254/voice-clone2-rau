"""Shared pytest fixtures for the Hamlet.AI test suite."""
from __future__ import annotations

from pathlib import Path

import pytest

from hamlet_ai.config import AppConfig, ScriptGenSettings, VoiceCloneSettings, ensure_dirs


@pytest.fixture
def tmp_base_dirs(tmp_path: Path) -> dict[str, Path]:
    """Lay out the workspace directories used by both tools under ``tmp_path``."""
    vc = tmp_path / "VOICE-CLONE"
    sg = tmp_path / "LLM-H"
    ws = tmp_path / "script_gen_workspace"
    return {"voice_clone": vc, "script_gen": sg, "workspace": ws}


@pytest.fixture
def cfg(tmp_base_dirs: dict[str, Path]) -> AppConfig:
    """Real-API AppConfig pointed at tmp dirs. dry_run=False so tests exercise mocked HTTP."""
    config = AppConfig(
        voice_clone=VoiceCloneSettings(
            base_dir=tmp_base_dirs["voice_clone"],
            clone_poll_interval=0.0,
            clone_timeout=2.0,
        ),
        script_gen=ScriptGenSettings(
            base_dir=tmp_base_dirs["script_gen"],
            workspace_dir=tmp_base_dirs["workspace"],
        ),
        dry_run=False,
        elevenlabs_api_key="test-el-key",
        anthropic_api_key="test-an-key",
        openai_api_key="test-op-key",
    )
    ensure_dirs(config)
    return config


@pytest.fixture
def dry_cfg(cfg: AppConfig) -> AppConfig:
    cfg.dry_run = True
    return cfg


@pytest.fixture
def fake_clone_txt(cfg: AppConfig) -> Path:
    """Write a 3-entry clone.txt and return its path."""
    cfg.voice_clone.script_file.parent.mkdir(parents=True, exist_ok=True)
    cfg.voice_clone.script_file.write_text(
        "ghost_00_sample.mp3\n"
        "Hi, I'm Audience Burt. [pause] Nice to meet you.\n\n"
        "ghost_01_shakespeare.mp3\n"
        "List, list, O list!\n\n"
        "ghost_02_modern.mp3\n"
        "Very bad murder, [pause] as all murders are...\n",
        encoding="utf-8",
    )
    return cfg.voice_clone.script_file


@pytest.fixture
def fake_sample_audio(cfg: AppConfig) -> Path:
    """Drop a fake audio file into SAMPLE/ so clone_voice has something to upload."""
    path = cfg.voice_clone.sample_dir / "volunteer.mp3"
    path.write_bytes(b"FAKE_AUDIO_DATA_FOR_TESTS")
    return path
