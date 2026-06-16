"""TTS stage: synthesize each line to the workspace, timing each one."""
from __future__ import annotations

import time

from PySide6.QtCore import Signal, Slot
from PySide6.QtWidgets import (
    QLabel,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from hamlet_ai.config import AppConfig
from hamlet_ai.core.script_gen.character_voices import CharacterVoiceMap
from hamlet_ai.core.script_gen.tts import synthesize_line


class TtsStage(QWidget):
    finished = Signal(int, float)  # lines synthesized, total seconds

    def __init__(self, cfg: AppConfig, state, parent: QWidget | None = None):
        super().__init__(parent)
        self.cfg = cfg
        self.state = state

        layout = QVBoxLayout(self)
        self.run_btn = QPushButton("Synthesize All Lines")
        self.run_btn.clicked.connect(self.run_tts)
        layout.addWidget(self.run_btn)
        self.progress = QProgressBar()
        layout.addWidget(self.progress)
        self.status_label = QLabel("")
        layout.addWidget(self.status_label)
        layout.addStretch(1)

    @Slot()
    def run_tts(self) -> None:
        parsed = self.state.parsed_de
        if parsed is None or not parsed.lines:
            self.status_label.setText("Run the Splitter step first.")
            return
        voice_map = CharacterVoiceMap(self.cfg.script_gen.character_voices_path)
        out_dir = self.cfg.script_gen.workspace_dir / "valid_lines" / "German" / "output"
        out_dir.mkdir(parents=True, exist_ok=True)

        total = len(parsed.lines)
        self.progress.setRange(0, total)
        start = time.monotonic()
        done = 0
        for line in parsed.lines:
            voice_id = voice_map.resolve(line.character, overrides=self.state.voice_map)
            out = out_dir / f"{line.line_number:03d}-{line.character}.mp3"
            try:
                synthesize_line(self.cfg, line.dialogue, voice_id, out, log_fn=lambda *_: None)
                done += 1
            except Exception as e:  # noqa: BLE001
                self.status_label.setText(f"Line {line.line_number} failed: {e}")
            self.progress.setValue(done)
        elapsed = time.monotonic() - start
        self.status_label.setText(f"✅ {done}/{total} lines in {elapsed:.2f}s")
        self.finished.emit(done, elapsed)
