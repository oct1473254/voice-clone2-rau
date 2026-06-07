"""Inline play button for table cells.

Owns no audio state of its own — emits ``play_requested(path)`` and lets a
shared ``AudioPlayer`` in the parent tab actually decode the file.
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QPushButton, QWidget


class PlayButton(QPushButton):
    play_requested = Signal(object)  # Path

    def __init__(self, path: Path, parent: QWidget | None = None):
        super().__init__("▶", parent)
        self.path = path
        self.setEnabled(path.exists())
        self.clicked.connect(self._emit_play)

    def _emit_play(self) -> None:
        if self.path.exists():
            self.play_requested.emit(self.path)

    def refresh(self) -> None:
        self.setEnabled(self.path.exists())
