"""Countdown timer widget for the Record tab.

Three discrete phases:
    PREP   — "3 / 2 / 1" pre-roll before recording starts
    RECORD — count down from target_seconds to 0
    DONE   — fired ``finished`` signal

Driven by a QTimer at 10Hz so the seconds-display feels responsive.
"""
from __future__ import annotations

import enum

from PySide6.QtCore import QTimer, Signal, Slot
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget


class CountdownPhase(str, enum.Enum):
    IDLE = "idle"
    PREP = "prep"
    RECORD = "record"
    DONE = "done"


class CountdownTimer(QWidget):
    prep_finished = Signal()  # 3-2-1 done, time to call recorder.start()
    target_reached = Signal()  # countdown hit 0 → caller should call recorder.stop()
    tick = Signal(float, str)  # (remaining_seconds, phase)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        self.label = QLabel("—", self)
        self.label.setStyleSheet("font-size: 48px; font-weight: bold;")
        layout.addWidget(self.label)

        self.phase = CountdownPhase.IDLE
        self.remaining = 0.0
        self.target_seconds = 0.0

        self._timer = QTimer(self)
        self._timer.setInterval(100)
        self._timer.timeout.connect(self._on_tick)

    @Slot(float)
    def start(self, target_seconds: float) -> None:
        """Begin the 3-2-1 prep countdown. Caller waits for ``prep_finished``."""
        self.target_seconds = max(0.0, target_seconds)
        self.phase = CountdownPhase.PREP
        self.remaining = 3.0
        self._update_label()
        self._timer.start()

    @Slot()
    def cancel(self) -> None:
        self._timer.stop()
        self.phase = CountdownPhase.IDLE
        self.remaining = 0.0
        self.label.setText("—")

    @Slot()
    def pause(self) -> None:
        """Freeze the countdown without losing phase/remaining (used when the
        recorder is paused). Resume with :meth:`resume`."""
        self._timer.stop()
        if self.phase is CountdownPhase.RECORD:
            self.label.setText(f"{self.remaining:0.1f} s — paused")

    @Slot()
    def resume(self) -> None:
        if self.phase in (CountdownPhase.PREP, CountdownPhase.RECORD):
            self._update_label()
            self._timer.start()

    @Slot(float)
    def update_remaining(self, remaining: float) -> None:
        """Called by the recorder (via duration_changed) once recording starts."""
        if self.phase is not CountdownPhase.RECORD:
            return
        self.remaining = max(0.0, self.target_seconds - remaining)
        self._update_label()
        if self.remaining <= 0.0:
            self._timer.stop()
            self.phase = CountdownPhase.DONE
            self.target_reached.emit()

    def _on_tick(self) -> None:
        if self.phase is CountdownPhase.PREP:
            self.remaining -= 0.1
            if self.remaining <= 0.0:
                self._timer.stop()
                self.phase = CountdownPhase.RECORD
                self.remaining = self.target_seconds
                self._update_label()
                self.prep_finished.emit()
                # Run a soft 1s safety timer so target_reached can still fire
                # even if the recorder never emits duration_changed (e.g. mocked).
                self._timer.start()
            else:
                self._update_label()
        elif self.phase is CountdownPhase.RECORD:
            # Recorder usually drives the display; this is a fallback that
            # keeps the label changing if duration_changed isn't wired.
            self.remaining = max(0.0, self.remaining - 0.1)
            self._update_label()
            if self.remaining <= 0.0:
                self._timer.stop()
                self.phase = CountdownPhase.DONE
                self.target_reached.emit()

    def _update_label(self) -> None:
        if self.phase is CountdownPhase.PREP:
            self.label.setText(f"Get ready… {int(self.remaining) + 1}")
            self.tick.emit(self.remaining, CountdownPhase.PREP.value)
        elif self.phase is CountdownPhase.RECORD:
            self.label.setText(f"{self.remaining:0.1f} s left")
            self.tick.emit(self.remaining, CountdownPhase.RECORD.value)
        else:
            self.label.setText("—")
