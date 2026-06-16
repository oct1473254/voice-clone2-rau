"""Voices stage: map each character to an ElevenLabs voice and persist it."""
from __future__ import annotations

from PySide6.QtCore import Signal, Slot
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from hamlet_ai.config import AppConfig
from hamlet_ai.core.script_gen.character_voices import CharacterVoiceMap


class VoicesStage(QWidget):
    saved = Signal()

    def __init__(self, cfg: AppConfig, state, available_voices=None, parent: QWidget | None = None):
        super().__init__(parent)
        self.cfg = cfg
        self.state = state
        # available_voices: list of (voice_id, label); injectable for tests.
        self.available_voices = available_voices or [("default", "Default")]
        self.voice_map = CharacterVoiceMap(cfg.script_gen.character_voices_path)
        self._combos: dict[str, QComboBox] = {}

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Assign a voice to each character:"))
        self.form = QFormLayout()
        layout.addLayout(self.form)

        self.save_btn = QPushButton("Save Map")
        self.save_btn.clicked.connect(self.save_map)
        layout.addWidget(self.save_btn)
        layout.addStretch(1)

    def on_enter(self) -> None:
        self._rebuild()

    def _rebuild(self) -> None:
        # Clear existing rows.
        while self.form.rowCount():
            self.form.removeRow(0)
        self._combos.clear()

        existing = self.voice_map.load()
        characters = self.state.parsed_de.characters if self.state.parsed_de else []
        for character in characters:
            combo = QComboBox()
            for voice_id, label in self.available_voices:
                combo.addItem(f"{label} ({voice_id})", voice_id)
            if character in existing:
                idx = combo.findData(existing[character])
                if idx >= 0:
                    combo.setCurrentIndex(idx)
            self.form.addRow(character, combo)
            self._combos[character] = combo

    @Slot()
    def save_map(self) -> None:
        mapping = {char: combo.currentData() for char, combo in self._combos.items()}
        self.voice_map.save(mapping)
        self.state.voice_map = mapping
        self.saved.emit()
