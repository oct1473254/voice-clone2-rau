"""Generate stage: show the constructed prompt, run the LLM, edit the result."""
from __future__ import annotations

from PySide6.QtCore import Signal, Slot
from PySide6.QtWidgets import (
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from hamlet_ai.config import AppConfig
from hamlet_ai.core.script_gen.llm import LLMClients, LLMProvider, generate
from hamlet_ai.core.script_gen.prompt import construct_prompt


class GenerateStage(QWidget):
    generated = Signal(str)

    def __init__(self, cfg: AppConfig, state, clients: LLMClients | None = None, parent: QWidget | None = None):
        super().__init__(parent)
        self.cfg = cfg
        self.state = state
        self.clients = clients

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Constructed prompt:"))
        self.prompt_view = QPlainTextEdit()
        self.prompt_view.setReadOnly(True)
        layout.addWidget(self.prompt_view)

        self.generate_btn = QPushButton("Generate")
        self.generate_btn.clicked.connect(self._on_generate)
        layout.addWidget(self.generate_btn)

        layout.addWidget(QLabel("Generated German scene (editable):"))
        self.result_edit = QPlainTextEdit()
        layout.addWidget(self.result_edit, stretch=1)

        self.status_label = QLabel("")
        layout.addWidget(self.status_label)

    def on_enter(self) -> None:
        if self.state.params is not None:
            self.prompt_view.setPlainText(construct_prompt(self.state.params))

    @Slot()
    def _on_generate(self) -> None:
        if self.state.params is None:
            self.status_label.setText("⚠️ Complete the Input step first.")
            return
        provider = LLMProvider(self.cfg.script_gen.default_provider)
        model = self.cfg.script_gen.models[provider.value]
        try:
            text = generate(
                construct_prompt(self.state.params),
                provider,
                model,
                anthropic_api_key=self.cfg.anthropic_api_key,
                openai_api_key=self.cfg.openai_api_key,
                clients=self.clients,
            )
        except Exception as e:  # noqa: BLE001
            self.status_label.setText(f"⚠️ Generation failed: {e}")
            return
        self.result_edit.setPlainText(text)
        self.save()
        self.status_label.setText("✅ Generated.")
        self.generated.emit(text)

    def save(self) -> None:
        self.state.german_text = self.result_edit.toPlainText()
