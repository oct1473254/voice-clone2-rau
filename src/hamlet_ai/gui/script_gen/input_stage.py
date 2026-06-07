"""Input stage: collect ScriptGenParams + pick LLM with a Test Connection probe."""
from __future__ import annotations

from PySide6.QtCore import Signal, Slot
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from hamlet_ai.config import AppConfig
from hamlet_ai.core.script_gen.prompt import ScriptGenParams


class InputStage(QWidget):
    validated = Signal(bool)

    def __init__(self, cfg: AppConfig, state, provider_tester=None, parent: QWidget | None = None):
        super().__init__(parent)
        self.cfg = cfg
        self.state = state
        self.provider_tester = provider_tester  # (provider, cfg) -> (ok, msg)

        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.play_edit = QLineEdit()
        form.addRow("Play", self.play_edit)
        self.scene_edit = QLineEdit()
        form.addRow("Scene", self.scene_edit)
        self.count_spin = QSpinBox()
        self.count_spin.setRange(2, 4)
        form.addRow("Character count", self.count_spin)
        self.character_edit = QLineEdit()
        form.addRow("Character to include", self.character_edit)
        self.include_edit = QLineEdit()
        form.addRow("Incorporate", self.include_edit)
        self.style_edit = QLineEdit()
        form.addRow("Style", self.style_edit)

        self.provider_combo = QComboBox()
        for p in ("anthropic", "openai", "ollama"):
            self.provider_combo.addItem(p)
        self.provider_combo.setCurrentText(cfg.script_gen.default_provider)
        form.addRow("LLM provider", self.provider_combo)
        layout.addLayout(form)

        self.test_btn = QPushButton("Test Connection")
        self.test_btn.clicked.connect(self._on_test_connection)
        layout.addWidget(self.test_btn)

        self.status_label = QLabel("")
        layout.addWidget(self.status_label)
        layout.addStretch(1)

    def collect_params(self) -> ScriptGenParams:
        return ScriptGenParams(
            play_name=self.play_edit.text().strip(),
            scene_name=self.scene_edit.text().strip(),
            character_count=self.count_spin.value(),
            character_name=self.character_edit.text().strip(),
            include=self.include_edit.text().strip(),
            style=self.style_edit.text().strip(),
        )

    def validate(self) -> list[str]:
        params = self.collect_params()
        errors = params.validate()
        if not errors:
            self.state.params = params
            self.cfg.script_gen.default_provider = self.provider_combo.currentText()
            self.status_label.setText("✅ Inputs valid.")
        else:
            self.status_label.setText("⚠️ " + "; ".join(errors))
        self.validated.emit(not errors)
        return errors

    @Slot()
    def _on_test_connection(self) -> None:
        provider = self.provider_combo.currentText()
        tester = self.provider_tester
        if tester is None:
            from hamlet_ai.core.script_gen.llm import test_connection as tester
        try:
            ok, msg = tester(provider, self.cfg)
        except Exception as e:  # noqa: BLE001
            ok, msg = False, str(e)
        self.status_label.setText(("✅ " if ok else "⚠️ ") + msg)
