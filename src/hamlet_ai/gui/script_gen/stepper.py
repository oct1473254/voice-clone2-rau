"""Script Gen stepper shell + shared state passed between stages."""
from __future__ import annotations

from dataclasses import dataclass, field

from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from hamlet_ai.config import AppConfig
from hamlet_ai.core.script_gen.line_splitter import ParsedScript
from hamlet_ai.core.script_gen.prompt import ScriptGenParams


@dataclass
class ScriptGenState:
    params: ScriptGenParams | None = None
    english_text: str = ""
    parsed_en: ParsedScript | None = None
    parsed_de: ParsedScript | None = None
    voice_map: dict[str, str] = field(default_factory=dict)


STEP_NAMES = ("Input", "Generate", "Splitter", "Translation", "Voices", "TTS", "Export")


class ScriptGenTab(QWidget):
    def __init__(self, cfg: AppConfig, parent: QWidget | None = None):
        super().__init__(parent)
        self.cfg = cfg
        self.state = ScriptGenState()

        layout = QVBoxLayout(self)
        self.step_label = QLabel()
        layout.addWidget(self.step_label)

        self.stack = QStackedWidget()
        layout.addWidget(self.stack, stretch=1)

        # Import here to avoid a circular import at module load.
        from hamlet_ai.gui.script_gen.export_stage import ExportStage
        from hamlet_ai.gui.script_gen.generate_stage import GenerateStage
        from hamlet_ai.gui.script_gen.input_stage import InputStage
        from hamlet_ai.gui.script_gen.splitter_stage import SplitterStage
        from hamlet_ai.gui.script_gen.translation_stage import TranslationStage
        from hamlet_ai.gui.script_gen.tts_stage import TtsStage
        from hamlet_ai.gui.script_gen.voices_stage import VoicesStage

        self.stages = [
            InputStage(cfg, self.state),
            GenerateStage(cfg, self.state),
            SplitterStage(cfg, self.state),
            TranslationStage(cfg, self.state),
            VoicesStage(cfg, self.state),
            TtsStage(cfg, self.state),
            ExportStage(cfg, self.state),
        ]
        for stage in self.stages:
            self.stack.addWidget(stage)

        nav = QHBoxLayout()
        self.back_btn = QPushButton("◀ Back")
        self.back_btn.clicked.connect(self.go_back)
        nav.addWidget(self.back_btn)
        nav.addStretch(1)
        self.next_btn = QPushButton("Next ▶")
        self.next_btn.clicked.connect(self.go_next)
        nav.addWidget(self.next_btn)
        layout.addLayout(nav)

        self._update_step_ui()

    @property
    def current_index(self) -> int:
        return self.stack.currentIndex()

    def go_next(self) -> None:
        # Let the current stage refresh the next one as it becomes visible.
        if self.current_index < len(self.stages) - 1:
            self.stack.setCurrentIndex(self.current_index + 1)
            self._on_enter_stage()
            self._update_step_ui()

    def go_back(self) -> None:
        if self.current_index > 0:
            self.stack.setCurrentIndex(self.current_index - 1)
            self._on_enter_stage()
            self._update_step_ui()

    def _on_enter_stage(self) -> None:
        stage = self.stages[self.current_index]
        if hasattr(stage, "on_enter"):
            stage.on_enter()

    def _update_step_ui(self) -> None:
        i = self.current_index
        self.step_label.setText(f"Step {i + 1}/{len(STEP_NAMES)}: {STEP_NAMES[i]}")
        self.back_btn.setEnabled(i > 0)
        self.next_btn.setEnabled(i < len(self.stages) - 1)
