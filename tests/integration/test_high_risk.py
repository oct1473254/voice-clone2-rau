"""Step 17 — high-risk integration tests.

These guard the show-night-critical invariants the revised plan calls out:
no cleanup-during-clone race, DRY_RUN safety without an API key, playable
dry-run audio, atomic writes, consent gating, label-preserving translation,
tolerant splitting, fixed QLab filenames, the restore-last-good rescue path,
graceful provider-connection failures, redacted logs, the poll-loop retry, and
the performance-budget timing.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from hamlet_ai.consent import ConsentNotProvided, new_consent
from hamlet_ai.core.voice_clone import pipeline
from hamlet_ai.core.voice_clone.pipeline import run_show


def _noop(*_a, **_k) -> None:
    pass


# ---------- pipeline ordering / race ---------------------------------------

def test_pipeline_cleanup_does_not_move_current_sample(dry_cfg, fake_clone_txt, fake_sample_audio):
    """The volunteer sample is copied into the run, never moved out of SAMPLE/."""
    run = run_show(dry_cfg, consent=new_consent("vol", "keep"), log_fn=_noop)
    # Original sample is still in SAMPLE/ (not relocated mid-clone)...
    assert fake_sample_audio.exists()
    # ...and the run kept its own copy.
    assert (run.sample_dir / fake_sample_audio.name).exists()


def test_qlab_filenames_remain_fixed(dry_cfg, fake_clone_txt, fake_sample_audio):
    run_show(dry_cfg, consent=new_consent("vol", "keep"), log_fn=_noop)
    produced = sorted(p.name for p in dry_cfg.voice_clone.lines_dir.glob("*.mp3"))
    assert produced == [
        "ghost_00_sample.mp3",
        "ghost_01_shakespeare.mp3",
        "ghost_02_modern.mp3",
    ]


# ---------- DRY_RUN safety -------------------------------------------------

def test_dry_run_works_without_api_key(dry_cfg, fake_clone_txt, fake_sample_audio):
    dry_cfg.elevenlabs_api_key = None
    run = run_show(dry_cfg, consent=new_consent("vol", "keep"), log_fn=_noop)
    assert (dry_cfg.voice_clone.lines_dir / "ghost_00_sample.mp3").is_file()
    assert run.timings["within_budget"] is True


def test_dry_run_audio_is_playable(dry_cfg, fake_clone_txt, fake_sample_audio):
    run_show(dry_cfg, consent=new_consent("vol", "keep"), log_fn=_noop)
    mp3 = next(dry_cfg.voice_clone.lines_dir.glob("*.mp3"))
    data = mp3.read_bytes()
    assert len(data) > 0
    # ID3 header or a raw MPEG frame sync — i.e. a real audio file, not text.
    assert data[:3] == b"ID3" or data[0] == 0xFF


# ---------- atomic writes -------------------------------------------------

def test_atomic_writes_no_partial_file_visible(tmp_path, monkeypatch):
    from hamlet_ai.core import elevenlabs

    dest = tmp_path / "ghost_99.mp3"

    def boom(src, dst):  # noqa: ANN001
        raise OSError("simulated replace failure")

    monkeypatch.setattr(elevenlabs.os, "replace", boom)
    with pytest.raises(OSError):
        elevenlabs.write_audio_atomic(dest, b"audio-bytes")
    assert not dest.exists()                       # destination never appears
    assert not list(tmp_path.glob(".*.tmp"))       # tmp is cleaned up


# ---------- consent gating ------------------------------------------------

def test_consent_required_before_cloning(dry_cfg, fake_clone_txt, fake_sample_audio):
    with pytest.raises(ConsentNotProvided):
        run_show(dry_cfg, consent=None, log_fn=_noop)


# ---------- voice library remote delete -----------------------------------

def test_voice_library_remote_delete_called(tmp_path):
    from hamlet_ai.core.voice_clone.voice_library import VoiceEntry, VoiceLibrary

    lib = VoiceLibrary(tmp_path / "lib.json")
    lib.add(VoiceEntry.new("v1", "Vol", "/s/v.mp3", "v.mp3"))
    client = MagicMock()
    assert lib.delete_both("v1", client) is True
    client.delete_voice.assert_called_once_with("v1")
    assert lib.get("v1") is None


# ---------- translation label preservation --------------------------------

def test_translation_preserves_speaker_labels(monkeypatch):
    from hamlet_ai.core.script_gen.line_splitter import split_script
    from hamlet_ai.core.script_gen.llm import LLMClients
    from hamlet_ai.core.script_gen.translation import translate_scene
    from hamlet_ai.config import AppConfig

    parsed = split_script("HAMLET: To be.\nGERTRUDE: Speak, son.")

    class StubAnthropic:
        def messages_create(self, **kwargs):
            return SimpleNamespace(
                content=[SimpleNamespace(text="1. HAMLET: Sein.\n2. GERTRUDE: Sprich, Sohn.")]
            )

    cfg = AppConfig()
    cfg.anthropic_api_key = "k"
    out = translate_scene(
        parsed, cfg, clients=LLMClients(anthropic_factory=lambda _: StubAnthropic())
    )
    assert set(c for c in out.characters) == set(parsed.characters)
    assert [l.line_id for l in out.lines] == [l.line_id for l in parsed.lines]


# ---------- tolerant splitter ---------------------------------------------

def test_splitter_handles_colons_in_dialogue():
    from hamlet_ai.core.script_gen.line_splitter import split_script

    parsed = split_script("HAMLET: To eat: or not.")
    assert parsed.lines[0].character == "HAMLET"
    assert parsed.lines[0].dialogue == "To eat: or not."


def test_splitter_handles_accented_and_hyphenated_names():
    from hamlet_ai.core.script_gen.line_splitter import split_script

    parsed = split_script(
        "JEAN-PAUL: Bonjour.\nÉLODIE: Salut.\nKING'S MESSENGER: A letter."
    )
    assert {"JEAN-PAUL", "ÉLODIE", "KING'S MESSENGER"} <= set(parsed.characters)


# ---------- restore last good ---------------------------------------------

def test_restore_last_good_lines_copies_archive_into_lines(cfg):
    archive_sub = cfg.voice_clone.archive_dir / "20200101_000000"
    archive_sub.mkdir(parents=True, exist_ok=True)
    (archive_sub / "ghost_01.mp3").write_bytes(b"good-take")
    (archive_sub / "ghost_02.mp3").write_bytes(b"good-take-2")

    restored = pipeline.restore_last_good(cfg, log_fn=_noop)
    names = sorted(p.name for p in restored)
    assert names == ["ghost_01.mp3", "ghost_02.mp3"]
    assert (cfg.voice_clone.lines_dir / "ghost_01.mp3").read_bytes() == b"good-take"
    # Archive is untouched (copy, not move).
    assert (archive_sub / "ghost_01.mp3").exists()


# ---------- provider connection failures ----------------------------------

def test_provider_test_connection_handles_failure_gracefully():
    from hamlet_ai.core.script_gen.llm import LLMClients, test_connection
    from hamlet_ai.config import AppConfig

    def explode(_key):
        raise RuntimeError("network down")

    cfg = AppConfig()
    cfg.anthropic_api_key = "k"
    ok, message = test_connection(
        "anthropic", cfg, clients=LLMClients(anthropic_factory=explode)
    )
    assert ok is False
    assert "network down" in message
    # Health is recorded, not raised.
    assert cfg.provider_health["anthropic"].status == "failed"


# ---------- log redaction -------------------------------------------------

def test_logs_redact_api_keys():
    from hamlet_ai.redaction import redact

    # Build the key dynamically so it isn't a literal secret in the source tree.
    fake_key = "sk_" + "a" * 40
    masked = redact(f"uploading with key {fake_key}")
    assert fake_key not in masked
    assert "<REDACTED>" in masked


# ---------- get_voice_status retry (Fix #2) -------------------------------

def test_get_voice_status_retries_on_connection_error():
    import requests

    from hamlet_ai.core.elevenlabs import ElevenLabsClient

    session = MagicMock()
    ok = SimpleNamespace(status_code=200)
    session.get.side_effect = [requests.ConnectionError("blip"), ok]
    client = ElevenLabsClient(api_key="k", session=session, sleep_fn=lambda _: None)
    assert client.get_voice_status("v1") == 200
    assert session.get.call_count == 2


def test_get_voice_status_returns_404_without_retry():
    from hamlet_ai.core.elevenlabs import ElevenLabsClient

    session = MagicMock()
    session.get.return_value = SimpleNamespace(status_code=404)
    client = ElevenLabsClient(api_key="k", session=session, sleep_fn=lambda _: None)
    assert client.get_voice_status("v1") == 404
    assert session.get.call_count == 1


# ---------- performance budget (Step 16) ----------------------------------

def test_run_show_flags_budget_overrun(dry_cfg, fake_clone_txt, fake_sample_audio):
    dry_cfg.voice_clone.target_total_seconds = 0.0  # force an overrun
    ticks = iter([0.0, 100.0, 200.0])  # start, clone-ready, done
    run = run_show(
        dry_cfg,
        consent=new_consent("vol", "keep"),
        log_fn=_noop,
        clock=lambda: next(ticks),
    )
    assert run.timings["within_budget"] is False
    assert run.timings["total_seconds"] == 200.0
    assert run.timings["clone_ready_seconds"] == 100.0
    # Timings are durably recorded in the run metadata + log.
    assert run.read_metadata()["timings"]["within_budget"] is False
    assert "within_budget=False" in run.log_path.read_text()


# ---------- CLI uses label-preserving translation (Fix #1) ----------------

def test_cli_script_gen_uses_per_line_translation(monkeypatch, tmp_path, capsys):
    """The CLI translates per line so the English split files stay label-aligned."""
    from hamlet_ai import cli
    from hamlet_ai.config import AppConfig, ScriptGenSettings, VoiceCloneSettings

    cfg = AppConfig(
        voice_clone=VoiceCloneSettings(base_dir=tmp_path / "VOICE-CLONE"),
        script_gen=ScriptGenSettings(
            base_dir=tmp_path / "LLM-H",
            workspace_dir=tmp_path / "ws",
        ),
        dry_run=True,
    )
    monkeypatch.setattr(cli, "default_config", lambda: cfg)

    # The LLM generates the performed (German) scene. Use cast members the CLI
    # actually requested (Hamlet + Horatio) so the splitter's allowed-cast filter
    # keeps both lines — this test is about translation alignment, not the cast.
    def fake_german(*_a, **_k):
        return "HAMLET: Sein.\nHORATIO: Sprich, Freund."

    monkeypatch.setattr("hamlet_ai.core.script_gen.llm.generate", fake_german)

    captured = {}

    def fake_translate_scene(parsed, _cfg, *a, **k):
        captured["called"] = True
        from dataclasses import replace

        new = [replace(p, dialogue=f"EN-{p.dialogue}") for p in parsed.lines]
        return replace(parsed, lines=new)

    monkeypatch.setattr(
        "hamlet_ai.core.script_gen.translation.translate_scene", fake_translate_scene
    )

    rc = cli.main(
        [
            "script-gen",
            "--character-one", "Ophelia",
            "--character-two", "Horatio",
            "--llm", "anthropic",
            "--no-tts",
            "--dry-run",
        ]
    )
    assert rc == 0
    assert captured.get("called") is True
    # German split files exist; the English translation carries the same labels.
    de_dir = cfg.script_gen.workspace_dir / "valid_lines" / "German"
    de_names = sorted(p.name for p in de_dir.glob("*.txt"))
    assert any("HAMLET" in n for n in de_names)
    assert any("HORATIO" in n for n in de_names)
    en_dir = cfg.script_gen.workspace_dir / "valid_lines" / "English"
    en_names = sorted(p.name for p in en_dir.glob("*.txt"))
    assert any("HAMLET" in n for n in en_names)
    assert any("HORATIO" in n for n in en_names)
