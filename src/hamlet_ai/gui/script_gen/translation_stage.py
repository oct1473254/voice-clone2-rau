"""Translation stage: per-line translation with a count-mismatch warning."""
from __future__ import annotations

from PySide6.QtCore import Signal, Slot
from PySide6.QtWidgets import (
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from hamlet_ai.config import AppConfig
from hamlet_ai.core.script_gen.llm import LLMClients
from hamlet_ai.core.script_gen.translation import TranslationCountMismatch, translate_scene


class TranslationStage(QWidget):
    translated = Signal(int)

    def __init__(
        self,
        cfg: AppConfig,
        state,
        target_language: str = "German",
        clients: LLMClients | None = None,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.cfg = cfg
        self.state = state
        self.target_language = target_language
        self.clients = clients

        layout = QVBoxLayout(self)
        self.warning_label = QLabel("")
        self.warning_label.setStyleSheet("color: #b71c1c; font-weight: bold;")
        layout.addWidget(self.warning_label)

        self.run_btn = QPushButton(f"Translate to {target_language}")
        self.run_btn.clicked.connect(self.run_translation)
        layout.addWidget(self.run_btn)

        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["character", "English", target_language])
        self.table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.table, stretch=1)

    @Slot()
    def run_translation(self) -> None:
        self.warning_label.setText("")
        parsed = self.state.parsed_en
        if parsed is None:
            self.warning_label.setText("Run the Splitter step first.")
            return
        try:
            translated = translate_scene(
                parsed, self.cfg, self.target_language, clients=self.clients
            )
        except TranslationCountMismatch as e:
            self.warning_label.setText(
                f"⚠️ Line count mismatch (got {e.got}, expected {e.expected}). "
                f"Review before continuing."
            )
            return
        self.state.parsed_de = translated

        self.table.setRowCount(len(parsed.lines))
        for r, (en, de) in enumerate(zip(parsed.lines, translated.lines)):
            self.table.setItem(r, 0, QTableWidgetItem(en.character))
            self.table.setItem(r, 1, QTableWidgetItem(en.dialogue))
            self.table.setItem(r, 2, QTableWidgetItem(de.dialogue))
        self.translated.emit(len(translated.lines))
