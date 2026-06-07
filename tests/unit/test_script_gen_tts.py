"""Step 6: script-gen TTS atomic writes + DRY_RUN behavior."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from hamlet_ai.core.elevenlabs import ElevenLabsClient
from hamlet_ai.core.script_gen.tts import synthesize_line


def test_dry_run_writes_placeholder(dry_cfg, tmp_path):
    out = tmp_path / "001-HAMLET.mp3"
    result = synthesize_line(
        dry_cfg, text="Words.", voice_id="vid", output_path=out, log_fn=lambda *_: None
    )
    assert result == out
    assert "DRY RUN" in out.read_text(encoding="utf-8")


def test_real_run_writes_audio_bytes(cfg, tmp_path):
    out = tmp_path / "001-HAMLET.mp3"
    client = MagicMock(spec=ElevenLabsClient)
    client.synthesize.return_value = b"\x00\x01MP3"
    result = synthesize_line(
        cfg, text="Words.", voice_id="vid", output_path=out,
        log_fn=lambda *_: None, client=client,
    )
    assert result == out
    assert out.read_bytes() == b"\x00\x01MP3"
    client.synthesize.assert_called_once()


def test_real_run_atomic_failure_leaves_no_partial(cfg, tmp_path, monkeypatch):
    out = tmp_path / "001-HAMLET.mp3"
    client = MagicMock(spec=ElevenLabsClient)
    client.synthesize.return_value = b"\x00MP3"
    monkeypatch.setattr("os.replace", lambda *a, **k: (_ for _ in ()).throw(OSError("disk full")))
    with pytest.raises(OSError):
        synthesize_line(cfg, "x", "vid", out, log_fn=lambda *_: None, client=client)
    assert not out.exists()
    # No leftover tmp
    assert list(tmp_path.glob(".001-HAMLET*")) == []


def test_real_run_missing_api_key_raises(cfg, tmp_path):
    cfg.elevenlabs_api_key = None
    out = tmp_path / "001-HAMLET.mp3"
    with pytest.raises(RuntimeError):
        synthesize_line(cfg, "x", "vid", out, log_fn=lambda *_: None)
