"""Unit tests for the doctor health checks."""
from __future__ import annotations

from datetime import datetime, timezone, timedelta

from hamlet_ai import doctor
from hamlet_ai.doctor import ERROR, OK, WARN, run_checks


def _results_by_name(report):
    return {r.name: r for r in report.results}


def _run(cfg, **kw):
    # Default to no external probes so tests stay offline.
    kw.setdefault("client_factory", None)
    kw.setdefault("connection_tester", None)
    kw.setdefault("audio_probe", None)
    return run_checks(cfg, **kw)


def test_exit_code_ok_when_all_green(dry_cfg, fake_clone_txt):
    # Seed a QLab file + clean sample so the warn-y checks pass.
    (dry_cfg.voice_clone.lines_dir / "ghost_00.mp3").write_bytes(b"x")
    report = _run(dry_cfg)
    by = _results_by_name(report)
    assert by["clone.txt"].status == OK
    assert by["QLab files"].status == OK
    assert report.exit_code in (0, 1)  # no errors


def test_missing_clone_txt_is_error(dry_cfg):
    report = _run(dry_cfg)
    by = _results_by_name(report)
    assert by["clone.txt"].status == ERROR
    assert report.exit_code == 2


def test_dry_run_without_key_is_warn_not_error(dry_cfg, fake_clone_txt):
    dry_cfg.elevenlabs_api_key = None
    report = _run(dry_cfg)
    by = _results_by_name(report)
    assert by["ElevenLabs key"].status == WARN


def test_live_run_without_key_is_error(cfg, fake_clone_txt):
    cfg.dry_run = False
    cfg.elevenlabs_api_key = None
    report = _run(cfg)
    by = _results_by_name(report)
    assert by["ElevenLabs key"].status == ERROR


def test_provider_checks_use_injected_tester(dry_cfg, fake_clone_txt):
    def tester(provider, cfg):
        return (provider != "ollama", f"{provider} probed")

    report = run_checks(
        dry_cfg, client_factory=None, connection_tester=tester, audio_probe=None
    )
    by = _results_by_name(report)
    assert by["LLM: anthropic"].status == OK
    assert by["LLM: ollama"].status == WARN


def test_expired_voice_warns(dry_cfg, fake_clone_txt):
    from hamlet_ai.core.voice_clone.voice_library import VoiceEntry, VoiceLibrary

    now = datetime(2026, 6, 7, tzinfo=timezone.utc)
    lib = VoiceLibrary(dry_cfg.voice_clone.voice_library_path)
    lib.add(
        VoiceEntry.new(
            "v1", "Burt", "/t/b.mp3", "b.mp3",
            retention_policy="delete_after_show",
            now=now - timedelta(hours=48),
        )
    )
    report = _run(dry_cfg, now=now)
    by = _results_by_name(report)
    assert by["Retention sweep"].status == WARN


def test_audio_probe_reports_devices(dry_cfg, fake_clone_txt):
    report = run_checks(
        dry_cfg,
        client_factory=None,
        connection_tester=None,
        audio_probe=lambda: [(0, "Built-in Mic")],
    )
    by = _results_by_name(report)
    assert by["Audio input"].status == OK


def test_format_report_contains_summary(dry_cfg, fake_clone_txt):
    report = _run(dry_cfg)
    text = doctor.format_report(report)
    assert "hamlet-ai doctor" in text
    assert "error(s)" in text
