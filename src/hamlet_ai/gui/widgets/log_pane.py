"""Shared log pane shown at the bottom of the main window."""
from __future__ import annotations

from PySide6.QtCore import Slot
from PySide6.QtWidgets import QPlainTextEdit, QWidget


class LogPane(QPlainTextEdit):
    """Read-only text area that any worker can pipe its ``log`` signal into."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.setMaximumBlockCount(5000)
        self.setPlaceholderText("Logs from running tasks appear here…")

    @Slot(str)
    def append_message(self, message: str) -> None:
        self.appendPlainText(message)
