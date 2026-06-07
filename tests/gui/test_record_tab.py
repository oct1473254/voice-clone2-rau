"""Step 11: Record tab — countdown → recorder.start → meter → auto-stop → buttons."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import numpy as np
import pytest
from PySide6.QtCore import QObject, Signal

from hamlet_ai.config import AppConfig, ScriptGenSettings, VoiceCloneSettings
from hamlet_ai.core.audio.recorder import AudioRecorder
from hamlet_ai.gui.voice_clone.record_tab import RecordTab
from hamlet_ai.gui.widgets.countdown_timer import CountdownPhase, CountdownTimer
from hamlet_ai.gui.widgets.level_meter import LevelMeter


# ---------- helpers -------------------------------------------------------

class FakeRecorder(QObject):
    """Drop-in for AudioRecorder; exposes the same signals + start/stop API."""
    level_changed = Signal(float)
    duration_changed = Signal(float)
    finished = Signal(object)
    error = Signal(str)

    def __init__(self):
        super().__init__()
        self.is_recording = False
        self.started_with: tuple[Path, float | None] | None = None
        self.stop_calls = 0

    def start(self, output_path, target_seconds=None):
        if self.is_recording:
            raise RuntimeError("already recording")
        self.is_recording = True
        self.started_with = (Path(output_path), target_seconds)

    def stop(self):
        self.stop_calls += 1
        self.is_recording = False
        if self.started_with is not None:
            self.finished.emit(self.started_with[0])

    @staticmethod
    def list_input_devices():
        return []


@pytest.fixture
def cfg(tmp_path) -> AppConfig:
    return AppConfig(
        voice_clone=VoiceCloneSettings(base_dir=tmp_path / "VOICE-CLONE", recording_target_seconds=2.0),
        script_gen=ScriptGenSettings(base_dir=tmp_path / "LLM-H", workspace_dir=tmp_path / "ws"),
        dry_run=True,
    )


# ---------- LevelMeter ---------------------------------------------------

def test_level_meter_scales_rms_to_progress_bar(qtbot):
    meter = LevelMeter()
    qtbot.addWidget(meter)
    meter.set_level(0.0)
    assert meter.value() == 0
    meter.set_level(0.5)
    assert 80 <= meter.value() <= 100
    meter.set_level(2.0)  # over-saturated input should clamp
    assert meter.value() == 100


# ---------- CountdownTimer ----------------------------------------------

def test_countdown_starts_in_prep_phase(qtbot):
    t = CountdownTimer()
    qtbot.addWidget(t)
    t.start(90.0)
    assert t.phase == CountdownPhase.PREP
    assert t.target_seconds == 90.0
    t.cancel()


def test_countdown_prep_finished_emits_signal(qtbot):
    t = CountdownTimer()
    qtbot.addWidget(t)
    # Use a tiny prep — simulate elapsed by setting remaining
    t.start(5.0)
    with qtbot.waitSignal(t.prep_finished, timeout=5000):
        # Fast-forward by manipulating remaining + ticking the internal timer
        t.remaining = 0.05
        t._on_tick()
    assert t.phase == CountdownPhase.RECORD


def test_countdown_update_remaining_during_record(qtbot):
    t = CountdownTimer()
    qtbot.addWidget(t)
    t.start(10.0)
    t.phase = CountdownPhase.RECORD  # skip prep
    t.update_remaining(3.0)  # 3s elapsed of 10s target
    assert t.remaining == pytest.approx(7.0)


def test_countdown_target_reached_when_remaining_hits_zero(qtbot):
    t = CountdownTimer()
    qtbot.addWidget(t)
    t.start(10.0)
    t.phase = CountdownPhase.RECORD
    with qtbot.waitSignal(t.target_reached, timeout=2000):
        t.update_remaining(10.0)  # exactly at target
    assert t.phase == CountdownPhase.DONE


def test_countdown_cancel_resets_to_idle(qtbot):
    t = CountdownTimer()
    qtbot.addWidget(t)
    t.start(90.0)
    t.cancel()
    assert t.phase == CountdownPhase.IDLE
    assert t.label.text() == "—"


# ---------- RecordTab full flow ----------------------------------------

def test_record_tab_constructs(qtbot, cfg):
    tab = RecordTab(cfg, recorder=FakeRecorder())
    qtbot.addWidget(tab)
    assert tab.record_button.isEnabled()
    assert not tab.stop_button.isEnabled()
    assert not tab.clone_button.isEnabled()


def test_clicking_record_starts_countdown_and_disables_record(qtbot, cfg):
    tab = RecordTab(cfg, recorder=FakeRecorder())
    qtbot.addWidget(tab)
    tab._on_record_clicked()
    assert not tab.record_button.isEnabled()
    assert tab.stop_button.isEnabled()
    assert tab.countdown.phase == CountdownPhase.PREP


def test_prep_finished_triggers_recorder_start(qtbot, cfg):
    rec = FakeRecorder()
    tab = RecordTab(cfg, recorder=rec)
    qtbot.addWidget(tab)
    tab._on_record_clicked()
    tab._on_prep_finished()
    assert rec.is_recording is True
    out_path, target = rec.started_with
    assert out_path.parent == cfg.voice_clone.sample_dir
    assert target == cfg.voice_clone.recording_target_seconds


def test_auto_stop_triggers_when_target_reached(qtbot, cfg):
    rec = FakeRecorder()
    tab = RecordTab(cfg, recorder=rec)
    qtbot.addWidget(tab)
    tab._on_record_clicked()
    tab._on_prep_finished()
    tab._on_target_reached()
    assert rec.stop_calls == 1


def test_manual_stop_works_mid_recording(qtbot, cfg):
    rec = FakeRecorder()
    tab = RecordTab(cfg, recorder=rec)
    qtbot.addWidget(tab)
    tab._on_record_clicked()
    tab._on_prep_finished()
    tab._on_stop_clicked()
    assert rec.stop_calls == 1
    assert tab.countdown.phase == CountdownPhase.IDLE


def test_recorder_finished_enables_clone_button(qtbot, cfg, tmp_path):
    rec = FakeRecorder()
    tab = RecordTab(cfg, recorder=rec)
    qtbot.addWidget(tab)
    saved_path = tmp_path / "vol.wav"
    rec.finished.emit(saved_path)
    assert tab.clone_button.isEnabled()
    assert tab.retry_button.isEnabled()
    assert tab._last_recording == saved_path


def test_clone_button_emits_clone_requested(qtbot, cfg, tmp_path):
    rec = FakeRecorder()
    tab = RecordTab(cfg, recorder=rec)
    qtbot.addWidget(tab)
    saved_path = tmp_path / "vol.wav"
    rec.finished.emit(saved_path)
    captured: list[Path] = []
    tab.clone_requested.connect(captured.append)
    tab._on_clone_clicked()
    assert captured == [saved_path]


def test_retry_button_deletes_last_recording_and_resets(qtbot, cfg, tmp_path):
    rec = FakeRecorder()
    tab = RecordTab(cfg, recorder=rec)
    qtbot.addWidget(tab)
    saved_path = tmp_path / "vol.wav"
    saved_path.write_bytes(b"FAKE")
    rec.finished.emit(saved_path)
    tab._on_retry_clicked()
    assert not saved_path.exists()
    assert tab._last_recording is None
    assert not tab.clone_button.isEnabled()


def test_recorder_error_resets_buttons(qtbot, cfg):
    rec = FakeRecorder()
    tab = RecordTab(cfg, recorder=rec)
    qtbot.addWidget(tab)
    tab._on_record_clicked()
    rec.error.emit("mic denied")
    assert tab.record_button.isEnabled()
    assert not tab.stop_button.isEnabled()
    assert "mic denied" in tab.status_label.text()


def test_level_signal_pipes_to_meter(qtbot, cfg):
    rec = FakeRecorder()
    tab = RecordTab(cfg, recorder=rec)
    qtbot.addWidget(tab)
    rec.level_changed.emit(0.5)
    assert tab.level_meter.value() > 0


# ---------- Step 12: mic check -------------------------------------------

def test_mic_check_reports_rms(qtbot, cfg):
    tab = RecordTab(cfg, recorder=FakeRecorder())
    qtbot.addWidget(tab)
    rms = tab.mic_check(probe=lambda: 0.42)
    assert rms == 0.42
    assert "0.42" in tab.status_label.text()


def test_mic_check_handles_denied(qtbot, cfg):
    tab = RecordTab(cfg, recorder=FakeRecorder())
    qtbot.addWidget(tab)

    def boom():
        raise OSError("permission denied")

    rms = tab.mic_check(probe=boom)
    assert rms is None
    assert "failed" in tab.status_label.text().lower()
