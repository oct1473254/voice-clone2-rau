"""Ad-hoc TTS tab — type a line, synthesize it with the active voice to ADHOC/.

Useful for one-off improvised lines that aren't in clone.txt. Output lands in
``VOICE-CLONE/ADHOC/`` so it never collides with the QLab-watched ``LINES/``.
"""
from __future__ import annotations

import time
from pathlib import Path

from PySide6.QtCore import Signal, Slot
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from hamlet_ai.config import AppConfig
from hamlet_ai.core.voice_clone import pipeline


class AdhocTtsTab(QWidget):
    play_requested = Signal(object)  # Path
    generated = Signal(object)  # Path

    def __init__(self, cfg: AppConfig, voice_id: str | None = None, parent: QWidget | None = None):
        super().__init__(parent)
        self.cfg = cfg
        self.voice_id = voice_id

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Ad-hoc line text:"))
        self.text_edit = QPlainTextEdit()
        layout.addWidget(self.text_edit, stretch=1)

        form = QHBoxLayout()
        form.addWidget(QLabel("Output filename:"))
        self.filename_edit = QLineEdit(self._default_filename())
        form.addWidget(self.filename_edit, stretch=1)
        layout.addLayout(form)

        row = QHBoxLayout()
        self.generate_btn = QPushButton("Generate")
        self.generate_btn.clicked.connect(self._on_generate)
        row.addWidget(self.generate_btn)
        self.play_btn = QPushButton("Play")
        self.play_btn.setEnabled(False)
        self.play_btn.clicked.connect(self._on_play)
        row.addWidget(self.play_btn)
        layout.addLayout(row)

        self.status_label = QLabel("Idle.")
        layout.addWidget(self.status_label)
        self._last_output: Path | None = None

    def set_active_voice(self, voice_id: str) -> None:
        self.voice_id = voice_id

    def _default_filename(self) -> str:
        return f"adhoc_{time.strftime('%Y%m%d_%H%M%S')}.mp3"

    @Slot()
    def _on_generate(self) -> None:
        text = self.text_edit.toPlainText().strip()
        if not text:
            QMessageBox.warning(self, "Ad-hoc TTS", "Enter some text first.")
            return
        if not self.voice_id and not self.cfg.dry_run:
            QMessageBox.warning(self, "Ad-hoc TTS", "No active voice selected.")
            return
        filename = self.filename_edit.text().strip() or self._default_filename()
        try:
            path = pipeline.synthesize(
                self.cfg,
                self.voice_id or "dry_run_voice_id",
                text,
                filename,
                log_fn=lambda *_: None,
                output_dir=self.cfg.voice_clone.adhoc_dir,
            )
        except Exception as e:  # noqa: BLE001
            self.status_label.setText(f"Failed: {e}")
            QMessageBox.warning(self, "Ad-hoc TTS failed", str(e))
            return
        self._last_output = path
        self.play_btn.setEnabled(True)
        self.status_label.setText(f"Saved: {path}")
        self.generated.emit(path)

    @Slot()
    def _on_play(self) -> None:
        if self._last_output and self._last_output.exists():
            self.play_requested.emit(self._last_output)
