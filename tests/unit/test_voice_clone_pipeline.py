"""Step 3: voice-clone pipeline functions take cfg, no module-level state."""
from __future__ import annotations

import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from hamlet_ai.core.elevenlabs import ElevenLabsClient
from hamlet_ai.core.voice_clone import pipeline


# ---------- parse_script ---------------------------------------------------

def test_parse_script_returns_filename_text_tuples(fake_clone_txt):
    out = pipeline.parse_script(fake_clone_txt, log_fn=lambda *_: None)
    assert [name for name, _ in out] == [
        "ghost_00_sample.mp3",
        "ghost_01_shakespeare.mp3",
        "ghost_02_modern.mp3",
    ]
    assert "Audience Burt" in out[0][1]


def test_parse_script_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        pipeline.parse_script(tmp_path / "does_not_exist.txt", log_fn=lambda *_: None)


def test_parse_script_skips_malformed_block(tmp_path):
    p = tmp_path / "clone.txt"
    p.write_text("just_filename_no_text\n\ngood.mp3\nText here.\n", encoding="utf-8")
    logs: list[str] = []
    out = pipeline.parse_script(p, log_fn=logs.append)
    assert [name for name, _ in out] == ["good.mp3"]
    assert any("Skipping malformed" in m for m in logs)


# ---------- cleanup --------------------------------------------------------

def test_cleanup_empty_lines_is_noop(cfg):
    archived = pipeline.cleanup(cfg, log_fn=lambda *_: None)
    assert archived is None


def test_cleanup_moves_lines_and_sample_to_archive(cfg):
    (cfg.voice_clone.lines_dir / "ghost_00_sample.mp3").write_bytes(b"a")
    (cfg.voice_clone.lines_dir / "ghost_01.mp3").write_bytes(b"b")
    (cfg.voice_clone.sample_dir / "vol.mp3").write_bytes(b"c")
    archived = pipeline.cleanup(cfg, log_fn=lambda *_: None)
    assert archived is not None
    assert (archived / "ghost_00_sample.mp3").is_file()
    assert (archived / "ghost_01.mp3").is_file()
    assert (archived / "vol.mp3").is_file()
    assert not any(cfg.voice_clone.lines_dir.iterdir())
    assert not any(cfg.voice_clone.sample_dir.iterdir())


def test_cleanup_timestamp_uses_oldest_lines_mtime(cfg):
    f1 = cfg.voice_clone.lines_dir / "a.mp3"
    f2 = cfg.voice_clone.lines_dir / "b.mp3"
    f1.write_bytes(b"a")
    f2.write_bytes(b"b")
    old = time.time() - 86400
    import os as _os
    _os.utime(f1, (old, old))
    archived = pipeline.cleanup(cfg, log_fn=lambda *_: None)
    assert archived is not None
    expected = time.strftime("%Y%m%d_%H%M%S", time.localtime(old))
    assert archived.name == expected


# ---------- clone_voice ----------------------------------------------------

def test_clone_voice_dry_run_returns_mock_id(dry_cfg, fake_sample_audio):
    voice_id = pipeline.clone_voice(dry_cfg, log_fn=lambda *_: None)
    assert voice_id == "dry_run_voice_id_12345"


def test_clone_voice_raises_when_sample_empty(cfg):
    # SAMPLE/ exists but empty
    with pytest.raises(FileNotFoundError):
        pipeline.clone_voice(cfg, log_fn=lambda *_: None)


def test_clone_voice_uses_injected_client(cfg, fake_sample_audio):
    client = MagicMock(spec=ElevenLabsClient)
    client.clone_voice.return_value = "voice-xyz"
    voice_id = pipeline.clone_voice(cfg, log_fn=lambda *_: None, client=client)
    assert voice_id == "voice-xyz"
    client.clone_voice.assert_called_once()
    args, kwargs = client.clone_voice.call_args
    assert kwargs["audio_filename"] == "volunteer.mp3"


def test_clone_voice_multiple_files_warns_and_picks_first(cfg):
    (cfg.voice_clone.sample_dir / "a.mp3").write_bytes(b"a")
    (cfg.voice_clone.sample_dir / "b.mp3").write_bytes(b"b")
    logs: list[str] = []
    client = MagicMock(spec=ElevenLabsClient)
    client.clone_voice.return_value = "voice-xyz"
    pipeline.clone_voice(cfg, log_fn=logs.append, client=client)
    assert any("Multiple files" in m for m in logs)
    # First alphabetically is "a.mp3"
    _, kwargs = client.clone_voice.call_args
    assert kwargs["audio_filename"] == "a.mp3"


# ---------- wait_for_voice -------------------------------------------------

def test_wait_for_voice_dry_run_short_circuits(dry_cfg):
    out = pipeline.wait_for_voice(dry_cfg, "vid", log_fn=lambda *_: None)
    assert out == "vid"


def test_wait_for_voice_returns_immediately_on_200(cfg):
    client = MagicMock(spec=ElevenLabsClient)
    client.get_voice_status.return_value = 200
    sleep = MagicMock()
    out = pipeline.wait_for_voice(cfg, "vid", log_fn=lambda *_: None, sleep_fn=sleep, client=client)
    assert out == "vid"
    sleep.assert_not_called()


def test_wait_for_voice_polls_until_ready(cfg):
    cfg.voice_clone.clone_poll_interval = 0.1
    cfg.voice_clone.clone_timeout = 5.0
    client = MagicMock(spec=ElevenLabsClient)
    client.get_voice_status.side_effect = [404, 404, 200]
    sleep = MagicMock()
    out = pipeline.wait_for_voice(cfg, "vid", log_fn=lambda *_: None, sleep_fn=sleep, client=client)
    assert out == "vid"
    assert sleep.call_count == 2  # slept twice (between the two 404s)


def test_wait_for_voice_timeout_raises(cfg):
    cfg.voice_clone.clone_poll_interval = 1.0
    cfg.voice_clone.clone_timeout = 2.0
    client = MagicMock(spec=ElevenLabsClient)
    client.get_voice_status.return_value = 404
    with pytest.raises(TimeoutError):
        pipeline.wait_for_voice(cfg, "vid", log_fn=lambda *_: None, sleep_fn=lambda _: None, client=client)


def test_wait_for_voice_unexpected_status_raises(cfg):
    client = MagicMock(spec=ElevenLabsClient)
    client.get_voice_status.return_value = 500
    with pytest.raises(RuntimeError):
        pipeline.wait_for_voice(cfg, "vid", log_fn=lambda *_: None, sleep_fn=lambda _: None, client=client)


# ---------- synthesize -----------------------------------------------------

def test_synthesize_dry_run_writes_playable_silent_audio(dry_cfg):
    """DRY_RUN must produce a real audio file QLab and the in-app player can decode."""
    out = pipeline.synthesize(dry_cfg, "vid", "Hello world", "ghost_00_sample.wav", log_fn=lambda *_: None)
    assert out.is_file()
    from hamlet_ai.core.audio.silent_audio import is_valid_wav
    assert is_valid_wav(out)


def test_synthesize_dry_run_mp3_extension_produces_audio_bytes(dry_cfg):
    out = pipeline.synthesize(dry_cfg, "vid", "Hi", "ghost_00_sample.mp3", log_fn=lambda *_: None)
    assert out.is_file()
    head = out.read_bytes()[:4]
    # Either real MP3 or WAV fallback — both are valid audio
    assert head.startswith(b"ID3") or head[:2] in (b"\xff\xfb", b"\xff\xf3", b"\xff\xfa") or head == b"RIFF"


def test_synthesize_writes_audio_bytes_atomically(cfg):
    client = MagicMock(spec=ElevenLabsClient)
    client.synthesize.return_value = b"\x00MP3"
    out = pipeline.synthesize(
        cfg, "vid", "Hello", "ghost_00_sample.mp3", log_fn=lambda *_: None, client=client
    )
    assert out.is_file()
    assert out.read_bytes() == b"\x00MP3"
    # No leftover tmp file
    assert not list(cfg.voice_clone.lines_dir.glob(".*.tmp"))


def test_synthesize_atomic_failed_write_leaves_no_partial(cfg, monkeypatch):
    client = MagicMock(spec=ElevenLabsClient)
    client.synthesize.return_value = b"\x00MP3"

    def boom(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr("os.replace", boom)
    with pytest.raises(OSError):
        pipeline.synthesize(cfg, "vid", "Hi", "ghost_00_sample.mp3", log_fn=lambda *_: None, client=client)
    final = cfg.voice_clone.lines_dir / "ghost_00_sample.mp3"
    assert not final.exists()


# ---------- generate_lines -------------------------------------------------

def test_generate_lines_calls_synthesize_per_entry(dry_cfg):
    lines = [("a.mp3", "Alpha"), ("b.mp3", "Beta"), ("c.mp3", "Gamma")]
    written = pipeline.generate_lines(dry_cfg, "vid", lines, log_fn=lambda *_: None)
    assert len(written) == 3
    for path in written:
        assert path.is_file()


def test_generate_lines_emits_progress(dry_cfg):
    lines = [("a.mp3", "Alpha"), ("b.mp3", "Beta")]
    calls: list[tuple[int, int]] = []
    pipeline.generate_lines(dry_cfg, "vid", lines, log_fn=lambda *_: None, progress_fn=lambda d, t: calls.append((d, t)))
    assert calls == [(1, 2), (2, 2)]


def test_generate_lines_continues_on_per_line_failure(cfg):
    client = MagicMock(spec=ElevenLabsClient)
    client.synthesize.side_effect = [b"ok1", RuntimeError("boom"), b"ok3"]
    lines = [("a.mp3", "A"), ("b.mp3", "B"), ("c.mp3", "C")]
    written = pipeline.generate_lines(cfg, "vid", lines, log_fn=lambda *_: None, client=client)
    # Two succeeded, one failed
    assert len(written) == 2


# ---------- run_show -------------------------------------------------------

def test_run_show_dry_run_end_to_end(dry_cfg, fake_clone_txt, fake_sample_audio):
    pipeline.run_show(dry_cfg, log_fn=lambda *_: None)
    out_files = sorted(p.name for p in dry_cfg.voice_clone.lines_dir.iterdir())
    assert out_files == ["ghost_00_sample.mp3", "ghost_01_shakespeare.mp3", "ghost_02_modern.mp3"]
