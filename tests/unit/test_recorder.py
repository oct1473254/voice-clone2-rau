"""Step 8: AudioRecorder behavior with mocked sounddevice."""
from __future__ import annotations

import time
from pathlib import Path
from unittest.mock import MagicMock

import numpy as np
import pytest

from hamlet_ai.core.audio import recorder as recorder_mod
from hamlet_ai.core.audio.recorder import AudioRecorder


@pytest.fixture
def mock_sd(monkeypatch):
    fake = MagicMock()
    monkeypatch.setattr(recorder_mod, "sd", fake)
    return fake


@pytest.fixture
def mock_sf(monkeypatch):
    written: list[tuple[str, np.ndarray, int]] = []

    def fake_write(path, data, samplerate, subtype=None):
        written.append((path, data, samplerate))

    monkeypatch.setattr(recorder_mod.sf, "write", fake_write)
    return written


def test_list_input_devices_filters_input_only(monkeypatch):
    fake = MagicMock()
    fake.query_devices.return_value = [
        {"name": "Speakers", "max_input_channels": 0},
        {"name": "Built-in Mic", "max_input_channels": 1},
        {"name": "USB Mic", "max_input_channels": 2},
    ]
    monkeypatch.setattr(recorder_mod, "sd", fake)
    out = AudioRecorder.list_input_devices()
    assert out == [(1, "Built-in Mic"), (2, "USB Mic")]


def test_list_input_devices_returns_empty_when_sd_unavailable(monkeypatch):
    monkeypatch.setattr(recorder_mod, "sd", None)
    assert AudioRecorder.list_input_devices() == []


def test_start_opens_input_stream(qtbot, mock_sd, tmp_path):
    rec = AudioRecorder()
    qtbot.addWidget = lambda *a, **k: None  # AudioRecorder isn't a widget
    rec.start(tmp_path / "vol.wav")
    mock_sd.InputStream.assert_called_once()
    assert rec.is_recording is True
    rec.stop()


def test_callback_emits_level_and_duration(qtbot, mock_sd, mock_sf, tmp_path):
    rec = AudioRecorder()
    rec.start(tmp_path / "vol.wav")
    levels: list[float] = []
    durations: list[float] = []
    rec.level_changed.connect(levels.append)
    rec.duration_changed.connect(durations.append)

    chunk = np.array([[0.5], [0.5], [0.5]], dtype=np.float32)
    rec._on_audio(chunk, 3, None, None)
    assert levels[-1] == pytest.approx(0.5, rel=0.01)
    assert durations[-1] >= 0
    rec.stop()


def test_stop_writes_wav_and_emits_finished(qtbot, mock_sd, mock_sf, tmp_path):
    rec = AudioRecorder()
    out = tmp_path / "vol.wav"
    rec.start(out)
    chunk = np.array([[0.1], [0.2], [0.3]], dtype=np.float32)
    rec._on_audio(chunk, 3, None, None)

    finished: list[Path] = []
    rec.finished.connect(finished.append)
    rec.stop()

    assert mock_sf, "soundfile.write should have been called"
    written_path, written_data, sr = mock_sf[0]
    assert written_path == str(out)
    assert sr == 48000
    assert np.array_equal(written_data, chunk)
    assert finished[0] == out
    assert rec.is_recording is False


def test_stop_without_data_writes_empty_wav(qtbot, mock_sd, mock_sf, tmp_path):
    rec = AudioRecorder()
    out = tmp_path / "vol.wav"
    rec.start(out)
    rec.stop()
    assert mock_sf, "soundfile.write must be called even if no audio captured"
    _, data, _ = mock_sf[0]
    assert data.shape[0] == 0


def test_start_while_already_recording_raises(qtbot, mock_sd, tmp_path):
    rec = AudioRecorder()
    rec.start(tmp_path / "a.wav")
    with pytest.raises(RuntimeError):
        rec.start(tmp_path / "b.wav")
    rec.stop()


def test_stop_when_not_recording_returns_none(qtbot, mock_sd):
    rec = AudioRecorder()
    assert rec.stop() is None


def test_start_failure_emits_error_signal(qtbot, mock_sd, tmp_path):
    mock_sd.InputStream.side_effect = OSError("no mic")
    rec = AudioRecorder()
    errors: list[str] = []
    rec.error.connect(errors.append)
    with pytest.raises(OSError):
        rec.start(tmp_path / "v.wav")
    assert errors and "no mic" in errors[0]


def test_target_seconds_triggers_auto_stop(qtbot, mock_sd, mock_sf, tmp_path):
    rec = AudioRecorder()
    rec.start(tmp_path / "v.wav", target_seconds=0.01)
    # Force elapsed to exceed target by manipulating start_time
    rec._start_time = time.monotonic() - 1.0
    chunk = np.array([[0.1]], dtype=np.float32)
    rec._on_audio(chunk, 1, None, None)
    assert rec._auto_stop_requested is True


def test_recorder_is_qobject_with_signals(qtbot):
    """level_changed / duration_changed / finished / error must be Signals."""
    from PySide6.QtCore import Signal as SigType  # noqa: F401
    rec = AudioRecorder()
    # If these weren't Signals, connect() would raise on a non-callable.
    rec.level_changed.connect(lambda _: None)
    rec.duration_changed.connect(lambda _: None)
    rec.finished.connect(lambda _: None)
    rec.error.connect(lambda _: None)


def test_default_samplerate_is_48k():
    rec = AudioRecorder()
    assert rec.samplerate == 48000
    assert rec.channels == 1
