"""A big, colored status pill for the bottom status bar.

States map to a background color + label so the operator can read the app's
state across the room: Ready / Recording / Cloning / Generating / QLab Ready /
Failed / DRY_RUN / No API Key.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QWidget


_STATE_COLORS = {
    "ready": ("#2e7d32", "Ready"),
    "recording": ("#c62828", "Recording"),
    "cloning": ("#1565c0", "Cloning"),
    "generating": ("#6a1b9a", "Generating"),
    "qlab_ready": ("#2e7d32", "QLab Ready"),
    "failed": ("#b71c1c", "Failed"),
    "dry_run": ("#ef6c00", "DRY_RUN"),
    "no_api_key": ("#9e9e9e", "No API Key"),
}


class StatusPill(QLabel):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setAlignment(Qt.AlignCenter)
        self._state = "ready"
        self.set_state("ready")

    @property
    def state(self) -> str:
        return self._state

    def set_state(self, state: str, text: str | None = None) -> None:
        color, default_label = _STATE_COLORS.get(state, ("#9e9e9e", state))
        self._state = state
        self.setText(text or default_label)
        self.setStyleSheet(
            f"background-color: {color}; color: white; font-weight: bold; "
            f"padding: 4px 12px; border-radius: 6px;"
        )
