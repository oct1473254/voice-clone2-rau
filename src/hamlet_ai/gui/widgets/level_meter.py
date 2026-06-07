"""Vertical level meter driven by AudioRecorder.level_changed."""
from __future__ import annotations

from PySide6.QtCore import Qt, Slot
from PySide6.QtWidgets import QProgressBar, QWidget


class LevelMeter(QProgressBar):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setOrientation(Qt.Orientation.Vertical)
        self.setRange(0, 100)
        self.setValue(0)
        self.setTextVisible(False)
        self.setMinimumWidth(28)

    @Slot(float)
    def set_level(self, rms: float) -> None:
        """``rms`` is a 0..1 value; scale to 0..100 with mild amplification."""
        amplified = min(1.0, rms * 3.0)
        self.setValue(int(amplified * 100))
