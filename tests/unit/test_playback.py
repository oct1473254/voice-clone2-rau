"""Step 8: AudioPlayer wraps QMediaPlayer with normalized signals."""
from __future__ import annotations

from pathlib import Path

import pytest

from PySide6.QtMultimedia import QMediaPlayer

from hamlet_ai.core.audio.playback import AudioPlayer


def test_player_constructs(qtbot):
    p = AudioPlayer()
    assert p is not None


def test_play_sets_source_and_calls_play(qtbot, tmp_path, monkeypatch):
    p = AudioPlayer()
    src_path = tmp_path / "x.mp3"
    src_path.write_bytes(b"\x00")
    called = {"setSource": False, "play": False}

    def fake_set_source(url):
        called["setSource"] = url.toLocalFile()

    monkeypatch.setattr(p._player, "setSource", fake_set_source)
    monkeypatch.setattr(p._player, "play", lambda: called.__setitem__("play", True))

    p.play(src_path)
    assert called["setSource"] == str(src_path)
    assert called["play"] is True


def test_pause_and_stop_delegate_to_qmediaplayer(qtbot, monkeypatch):
    p = AudioPlayer()
    called = {"pause": False, "stop": False, "seek": None}
    monkeypatch.setattr(p._player, "pause", lambda: called.__setitem__("pause", True))
    monkeypatch.setattr(p._player, "stop", lambda: called.__setitem__("stop", True))
    monkeypatch.setattr(p._player, "setPosition", lambda v: called.__setitem__("seek", v))

    p.pause()
    p.stop()
    p.seek(1234)
    assert called == {"pause": True, "stop": True, "seek": 1234}


def test_state_changed_emits_strings(qtbot):
    p = AudioPlayer()
    captured: list[str] = []
    p.state_changed.connect(captured.append)
    p._on_state(QMediaPlayer.PlaybackState.PlayingState)
    p._on_state(QMediaPlayer.PlaybackState.PausedState)
    p._on_state(QMediaPlayer.PlaybackState.StoppedState)
    assert captured == ["playing", "paused", "stopped"]


def test_error_signal_emits_error_state(qtbot):
    p = AudioPlayer()
    captured: list[str] = []
    p.state_changed.connect(captured.append)
    p._on_error(QMediaPlayer.Error.ResourceError, "broken file")
    assert captured == ["error"]


def test_position_and_duration_signals_pass_through(qtbot):
    p = AudioPlayer()
    positions: list[int] = []
    durations: list[int] = []
    p.position_changed.connect(positions.append)
    p.duration_changed.connect(durations.append)
    p._player.positionChanged.emit(500)
    p._player.durationChanged.emit(12000)
    assert positions == [500]
    assert durations == [12000]
