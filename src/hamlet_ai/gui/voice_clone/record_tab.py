"""Record tab — the operator-facing voice capture UI.

Flow:
    1. Operator picks an input device, confirms target duration.
    2. Click Record → 3-2-1 prep overlay, then recorder.start() with target.
    3. Live count-DOWN to 0 + vertical level meter.
    4. Auto-stop at 0; manual Stop available any time.
    5. After stop: Retry / Discard / "Clone This Recording".
"""
from __future__ import annotations

import time
from pathlib import Path

from PySide6.QtCore import Signal, Slot
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from hamlet_ai.config import AppConfig
from hamlet_ai.core.audio.playback import AudioPlayer
from hamlet_ai.core.audio.recorder import AudioRecorder
from hamlet_ai.gui.widgets.countdown_timer import CountdownTimer
from hamlet_ai.gui.widgets.level_meter import LevelMeter


class RecordTab(QWidget):
    recording_saved = Signal(object)  # Path
    clone_requested = Signal(object)  # Path — operator wants to clone this take

    def __init__(self, cfg: AppConfig, recorder: AudioRecorder | None = None, parent: QWidget | None = None):
        super().__init__(parent)
        self.cfg = cfg
        self.recorder = recorder or AudioRecorder(samplerate=cfg.voice_clone.recording_samplerate)
        self.player = AudioPlayer(self)
        self.player.state_changed.connect(self._on_player_state)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(14)

        heading = QLabel("Capture a volunteer's voice")
        heading.setObjectName("recordHeading")
        layout.addWidget(heading)

        form = QFormLayout()
        self.device_combo = QComboBox()
        self.device_combo.addItem("(default)", userData=None)
        for idx, name in AudioRecorder.list_input_devices():
            self.device_combo.addItem(f"{idx}: {name}", userData=idx)
        form.addRow("Input device", self.device_combo)

        self.filename_edit = QLineEdit(self._default_filename())
        form.addRow("Output file", self.filename_edit)

        self.target_label = QLabel(f"{cfg.voice_clone.recording_target_seconds:.0f} s")
        form.addRow("Target duration", self.target_label)

        layout.addLayout(form)

        meter_row = QHBoxLayout()
        self.level_meter = LevelMeter()
        meter_row.addWidget(self.level_meter)
        self.countdown = CountdownTimer()
        meter_row.addWidget(self.countdown, stretch=1)
        layout.addLayout(meter_row)

        # Primary control: one big Record button that doubles as Stop while live.
        self.record_button = QPushButton("● Record")
        self.record_button.setObjectName("bigRecordButton")
        self.record_button.setMinimumHeight(72)
        self.record_button.clicked.connect(self._on_record_clicked)
        layout.addWidget(self.record_button)

        # Transport row: Pause/Resume + Play (review the captured take).
        transport_row = QHBoxLayout()
        self.pause_button = QPushButton("⏸ Pause")
        self.pause_button.setObjectName("transportButton")
        self.pause_button.setMinimumHeight(44)
        self.pause_button.setEnabled(False)
        self.pause_button.clicked.connect(self._on_pause_clicked)
        transport_row.addWidget(self.pause_button)
        self.play_button = QPushButton("▶ Play")
        self.play_button.setObjectName("transportButton")
        self.play_button.setMinimumHeight(44)
        self.play_button.setEnabled(False)
        self.play_button.clicked.connect(self._on_play_clicked)
        transport_row.addWidget(self.play_button)
        self.stop_button = QPushButton("Stop")
        self.stop_button.setMinimumHeight(44)
        self.stop_button.setEnabled(False)
        self.stop_button.clicked.connect(self._on_stop_clicked)
        transport_row.addWidget(self.stop_button)
        layout.addLayout(transport_row)

        # Secondary row: mic check + post-take decisions.
        button_row = QHBoxLayout()
        self.mic_check_button = QPushButton("Mic check")
        self.mic_check_button.clicked.connect(self._on_mic_check_clicked)
        button_row.addWidget(self.mic_check_button)
        self.retry_button = QPushButton("Discard / Retry")
        self.retry_button.setEnabled(False)
        self.retry_button.clicked.connect(self._on_retry_clicked)
        button_row.addWidget(self.retry_button)
        self.clone_button = QPushButton("Clone This Recording")
        self.clone_button.setObjectName("cloneButton")
        self.clone_button.setEnabled(False)
        self.clone_button.clicked.connect(self._on_clone_clicked)
        button_row.addWidget(self.clone_button)
        layout.addLayout(button_row)

        self.status_label = QLabel("Idle.")
        layout.addWidget(self.status_label)
        layout.addStretch(1)

        self._playing = False

        self._last_recording: Path | None = None

        self.countdown.prep_finished.connect(self._on_prep_finished)
        self.countdown.target_reached.connect(self._on_target_reached)
        self._wire_recorder()

    # ---------- public ----------
    def set_recorder(self, recorder: AudioRecorder) -> None:
        self.recorder = recorder
        self._wire_recorder()

    def reset_for_next_take(self) -> None:
        self.player.stop()
        self.record_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        self.pause_button.setEnabled(False)
        self.pause_button.setText("⏸ Pause")
        self.play_button.setEnabled(False)
        self.play_button.setText("▶ Play")
        self.retry_button.setEnabled(False)
        self.clone_button.setEnabled(False)
        self.level_meter.set_level(0.0)
        self.countdown.cancel()
        self.status_label.setText("Idle.")
        self.filename_edit.setText(self._default_filename())

    # ---------- recorder wiring ----------
    def _wire_recorder(self) -> None:
        self.recorder.level_changed.connect(self.level_meter.set_level)
        self.recorder.duration_changed.connect(self.countdown.update_remaining)
        self.recorder.finished.connect(self._on_recorder_finished)
        self.recorder.error.connect(self._on_recorder_error)

    # ---------- slots ----------
    # ---------- mic check ----------
    def mic_check(self, probe=None) -> float | None:
        """Open a brief input stream and report RMS. Returns RMS, or None if denied.

        ``probe`` is injectable for tests; the default reads ~0.5s from the
        default input device via sounddevice. This method never shows a modal —
        the button handler surfaces guidance so the core logic stays headless.
        """
        try:
            rms = probe() if probe is not None else self._default_mic_probe()
        except Exception as e:  # noqa: BLE001 — mic likely denied/unavailable
            self.status_label.setText(f"Mic check failed: {e}")
            self._last_mic_error = str(e)
            return None
        self.status_label.setText(f"Mic OK — level {rms:.3f}")
        self._last_mic_error = None
        return rms

    def _default_mic_probe(self) -> float:
        import numpy as np
        import sounddevice as sd

        seconds = 0.5
        sr = self.cfg.voice_clone.recording_samplerate
        frames = sd.rec(int(seconds * sr), samplerate=sr, channels=1)
        sd.wait()
        return float(np.sqrt(np.mean(np.square(frames))))

    @Slot()
    def _on_mic_check_clicked(self) -> None:
        rms = self.mic_check()
        if rms is None:
            QMessageBox.warning(
                self,
                "Microphone unavailable",
                "Could not read from the microphone. On macOS, grant access in "
                "System Settings → Privacy & Security → Microphone, then retry.\n\n"
                f"Details: {getattr(self, '_last_mic_error', '')}",
            )

    @Slot()
    def _on_record_clicked(self) -> None:
        if self.recorder.is_recording:
            return
        self.player.stop()
        self.record_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        self.pause_button.setEnabled(True)
        self.pause_button.setText("⏸ Pause")
        self.play_button.setEnabled(False)
        self.retry_button.setEnabled(False)
        self.clone_button.setEnabled(False)
        self.status_label.setText("Get ready…")
        self.countdown.start(self.cfg.voice_clone.recording_target_seconds)

    @Slot()
    def _on_pause_clicked(self) -> None:
        """Toggle pause/resume on the live recording (and its countdown)."""
        if not getattr(self.recorder, "is_active", False):
            return
        if getattr(self.recorder, "is_paused", False):
            self.recorder.resume()
            self.countdown.resume()
            self.pause_button.setText("⏸ Pause")
            self.status_label.setText("Recording…")
        else:
            self.recorder.pause()
            self.countdown.pause()
            self.pause_button.setText("⏵ Resume")
            self.status_label.setText("Paused.")

    @Slot()
    def _on_play_clicked(self) -> None:
        """Review the captured take. Toggles play/pause on the AudioPlayer."""
        if self._last_recording is None or not self._last_recording.exists():
            return
        if self._playing:
            self.player.pause()
        else:
            self.player.play(self._last_recording)

    @Slot(str)
    def _on_player_state(self, state: str) -> None:
        self._playing = state == "playing"
        self.play_button.setText("⏸ Pause playback" if self._playing else "▶ Play")

    @Slot()
    def _on_prep_finished(self) -> None:
        out_path = self.cfg.voice_clone.sample_dir / self.filename_edit.text().strip()
        try:
            self.recorder.start(out_path, target_seconds=self.cfg.voice_clone.recording_target_seconds)
            self.status_label.setText("Recording…")
        except Exception as e:  # noqa: BLE001
            self.status_label.setText(f"Failed to start: {e}")
            self.record_button.setEnabled(True)
            self.stop_button.setEnabled(False)
            self.countdown.cancel()

    @Slot()
    def _on_target_reached(self) -> None:
        # Auto-stop only if the recorder hasn't already auto-stopped itself.
        if self.recorder.is_recording:
            self.recorder.stop()

    @Slot()
    def _on_stop_clicked(self) -> None:
        self.countdown.cancel()
        # Stop finalizes the take whether it is live or paused.
        if getattr(self.recorder, "is_active", self.recorder.is_recording):
            self.recorder.stop()
        self.stop_button.setEnabled(False)
        self.pause_button.setEnabled(False)
        self.pause_button.setText("⏸ Pause")

    @Slot()
    def _on_retry_clicked(self) -> None:
        if self._last_recording and self._last_recording.exists():
            try:
                self._last_recording.unlink()
            except OSError:
                pass
        self._last_recording = None
        self.reset_for_next_take()

    @Slot()
    def _on_clone_clicked(self) -> None:
        if self._last_recording is not None:
            self.clone_requested.emit(self._last_recording)

    @Slot(object)
    def _on_recorder_finished(self, path: Path) -> None:
        self._last_recording = path
        self.stop_button.setEnabled(False)
        self.pause_button.setEnabled(False)
        self.pause_button.setText("⏸ Pause")
        self.play_button.setEnabled(True)
        self.retry_button.setEnabled(True)
        self.clone_button.setEnabled(True)
        self.record_button.setEnabled(True)
        self.status_label.setText(f"Saved: {path}")
        self.recording_saved.emit(path)

    @Slot(str)
    def _on_recorder_error(self, message: str) -> None:
        self.status_label.setText(f"Error: {message}")
        self.countdown.cancel()
        self.record_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        self.pause_button.setEnabled(False)
        self.pause_button.setText("⏸ Pause")

    def _default_filename(self) -> str:
        return f"volunteer_{time.strftime('%Y%m%d_%H%M%S')}.wav"
