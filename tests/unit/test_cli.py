"""Step 7: CLI argument parsing + subcommand dispatch."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from hamlet_ai import cli


def test_help_lists_all_subcommands(capsys):
    cli.main([])
    out = capsys.readouterr().out
    assert "gui" in out
    assert "voice-clone" in out
    assert "script-gen" in out
    assert "doctor" in out


def test_doctor_runs_and_returns_exit_code(monkeypatch, tmp_path, capsys):
    cfg = _temp_cfg(tmp_path)
    monkeypatch.setattr(cli, "default_config", lambda: cfg)
    # Keep doctor hermetic — no network or microphone.
    import hamlet_ai.doctor as doctor_mod

    monkeypatch.setattr(doctor_mod, "_default_client_factory", lambda c: None)
    monkeypatch.setattr(doctor_mod, "_default_connection_tester", lambda p, c: (True, "ok"))
    monkeypatch.setattr(doctor_mod, "_default_audio_probe", lambda: [(0, "Mic")])
    # No clone.txt → doctor reports an error → exit code 2.
    rc = cli.main(["doctor"])
    out = capsys.readouterr().out
    assert "hamlet-ai doctor" in out
    assert rc == 2


def test_voice_clone_help(capsys):
    with pytest.raises(SystemExit):
        cli.main(["voice-clone", "--help"])
    out = capsys.readouterr().out
    assert "voice-clone" in out
    assert "--dry-run" in out


def test_script_gen_help(capsys):
    with pytest.raises(SystemExit):
        cli.main(["script-gen", "--help"])
    out = capsys.readouterr().out
    assert "--play" in out
    assert "--scene" in out
    assert "--character-count" in out
    assert "--llm" in out


def test_script_gen_requires_either_interactive_or_full_args(capsys, monkeypatch, tmp_path):
    monkeypatch.setattr(cli, "default_config", lambda: _temp_cfg(tmp_path))
    rc = cli.main(["script-gen", "--play", "Hamlet"])
    assert rc == 2
    err = capsys.readouterr().err
    assert "script-gen" in err.lower() or "required" in err.lower() or "--scene" in err


def test_voice_clone_routes_to_run_show_via_default_cfg(monkeypatch, tmp_path):
    called = {}

    def fake_run_show(cfg, consent=None, log_fn=print, **kwargs):
        called["cfg"] = cfg
        called["dry_run"] = cfg.dry_run
        called["consent"] = consent

    monkeypatch.setattr("hamlet_ai.core.voice_clone.pipeline.run_show", fake_run_show)
    monkeypatch.setattr(cli, "default_config", lambda: _temp_cfg(tmp_path))
    rc = cli.main(["voice-clone", "--dry-run", "--i-consent", "--volunteer", "Burt"])
    assert rc == 0
    assert called["dry_run"] is True
    assert called["consent"] is not None
    assert called["consent"].volunteer_label == "Burt"


def test_voice_clone_without_consent_flag_refuses(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(cli, "default_config", lambda: _temp_cfg(tmp_path))
    rc = cli.main(["voice-clone", "--dry-run"])
    assert rc == 2
    assert "consent" in capsys.readouterr().err.lower()


def test_script_gen_end_to_end_dry_run_via_cli(monkeypatch, tmp_path, capsys):
    """The CLI happy path should run prompt→LLM→split→tts→export end-to-end."""
    cfg = _temp_cfg(tmp_path)
    cfg.dry_run = True
    monkeypatch.setattr(cli, "default_config", lambda: cfg)

    # Stub the LLM dispatcher so we never hit a real SDK.
    def fake_generate(prompt, provider, model, **_):
        return "HAMLET: First line.\nGERTRUDE: Second line.\n"

    monkeypatch.setattr("hamlet_ai.core.script_gen.llm.generate", fake_generate)
    # translate.py also imports generate by reference — patch its symbol too.
    import hamlet_ai.core.script_gen.translation as translation_mod
    monkeypatch.setattr(translation_mod, "generate", fake_generate)

    rc = cli.main([
        "script-gen",
        "--play", "Hamlet",
        "--scene", "Act I, Scene 1",
        "--character-count", "2",
        "--character-name", "Polonius",
        "--include", "a microphone",
        "--style", "comic",
        "--no-translate",
        "--dry-run",
    ])
    assert rc == 0
    workspace = cfg.script_gen.workspace_dir
    assert (workspace / "english_scene.txt").is_file()
    assert (workspace / "valid_lines" / "English" / "001-HAMLET.txt").is_file()
    assert (workspace / "valid_lines" / "English" / "output" / "001-HAMLET.mp3").is_file()
    assert (cfg.script_gen.base_dir / "Audio" / "001-HAMLET.mp3").is_file()


# ---------- helpers -------------------------------------------------------

def _temp_cfg(tmp_path: Path):
    from hamlet_ai.config import AppConfig, ScriptGenSettings, VoiceCloneSettings

    return AppConfig(
        voice_clone=VoiceCloneSettings(
            base_dir=tmp_path / "VOICE-CLONE",
            clone_poll_interval=0.0,
            clone_timeout=1.0,
        ),
        script_gen=ScriptGenSettings(
            base_dir=tmp_path / "LLM-H",
            workspace_dir=tmp_path / "workspace",
        ),
        dry_run=True,
        elevenlabs_api_key="test",
        anthropic_api_key="test",
        openai_api_key="test",
    )


def test_subprocess_invocation_returns_zero():
    result = subprocess.run(
        [sys.executable, "-m", "hamlet_ai", "voice-clone", "--help"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert "voice-clone" in result.stdout
