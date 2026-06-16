"""Settings dialog for editing AppConfig.

Exposes the operator-tunable knobs. API keys are read-only (sourced from the
environment / ``.env``) — saving never writes them to disk.
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from hamlet_ai.config import AppConfig


class SettingsDialog(QDialog):
    def __init__(self, cfg: AppConfig, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("Hamlet.AI Settings")
        self.cfg = cfg

        layout = QVBoxLayout(self)
        self.tabs = QTabWidget(self)
        layout.addWidget(self.tabs)

        self._build_general_tab()
        self._build_llm_tab()
        self._build_elevenlabs_tab()

        buttons = QDialogButtonBox(
            QDialogButtonBox.Save | QDialogButtonBox.Cancel,
            parent=self,
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    # ---------- General ----------
    def _build_general_tab(self) -> None:
        tab = QWidget(self)
        form = QFormLayout(tab)

        self.dry_run_box = QCheckBox()
        self.dry_run_box.setChecked(self.cfg.dry_run)
        form.addRow("Default DRY_RUN", self.dry_run_box)

        self.voice_clone_dir = QLineEdit(str(self.cfg.voice_clone.base_dir))
        form.addRow("Voice Clone base dir", self.voice_clone_dir)

        self.script_gen_dir = QLineEdit(str(self.cfg.script_gen.base_dir))
        form.addRow("Script Gen base dir", self.script_gen_dir)

        self.workspace_dir = QLineEdit(str(self.cfg.script_gen.workspace_dir))
        form.addRow("Script Gen workspace", self.workspace_dir)

        self.recording_target = QDoubleSpinBox()
        self.recording_target.setRange(5.0, 600.0)
        self.recording_target.setSingleStep(5.0)
        self.recording_target.setSuffix(" s")
        self.recording_target.setValue(self.cfg.voice_clone.recording_target_seconds)
        form.addRow("Recording target duration", self.recording_target)

        self.tabs.addTab(tab, "General")

    # ---------- LLM ----------
    def _build_llm_tab(self) -> None:
        tab = QWidget(self)
        form = QFormLayout(tab)

        self.provider_combo = QComboBox()
        for p in ("anthropic", "openai", "ollama"):
            self.provider_combo.addItem(p)
        self.provider_combo.setCurrentText(self.cfg.script_gen.default_provider)
        form.addRow("Default provider", self.provider_combo)

        self.translation_combo = QComboBox()
        self.translation_combo.addItem("(use default)")
        for p in ("anthropic", "openai", "ollama"):
            self.translation_combo.addItem(p)
        if self.cfg.script_gen.translation_provider:
            self.translation_combo.setCurrentText(self.cfg.script_gen.translation_provider)
        form.addRow("Translation provider", self.translation_combo)

        self.model_inputs: dict[str, QLineEdit] = {}
        for p in ("anthropic", "openai", "ollama"):
            edit = QLineEdit(self.cfg.script_gen.models[p])
            self.model_inputs[p] = edit
            form.addRow(f"{p} model", edit)

        self.tabs.addTab(tab, "LLM")

    # ---------- ElevenLabs ----------
    def _build_elevenlabs_tab(self) -> None:
        tab = QWidget(self)
        form = QFormLayout(tab)

        label = QLabel(
            "ELEVENLABS_API_KEY is set." if self.cfg.elevenlabs_api_key else
            "ELEVENLABS_API_KEY is NOT set — add it to your .env file."
        )
        form.addRow("API key status", label)

        self.stability = QDoubleSpinBox()
        self.stability.setRange(0.0, 1.0)
        self.stability.setSingleStep(0.05)
        self.stability.setValue(float(self.cfg.voice_clone.voice_settings.get("stability", 0.3)))
        form.addRow("Voice stability", self.stability)

        self.similarity = QDoubleSpinBox()
        self.similarity.setRange(0.0, 1.0)
        self.similarity.setSingleStep(0.05)
        self.similarity.setValue(float(self.cfg.voice_clone.voice_settings.get("similarity_boost", 0.75)))
        form.addRow("Similarity boost", self.similarity)

        self.speed = QDoubleSpinBox()
        self.speed.setRange(0.5, 2.0)
        self.speed.setSingleStep(0.05)
        self.speed.setValue(float(self.cfg.voice_clone.voice_settings.get("speed", 1.2)))
        form.addRow("Speed", self.speed)

        self.tabs.addTab(tab, "ElevenLabs")

    # ---------- Apply changes back to cfg ----------
    def apply_to_cfg(self) -> AppConfig:
        self.cfg.dry_run = self.dry_run_box.isChecked()
        self.cfg.voice_clone.base_dir = Path(self.voice_clone_dir.text()).expanduser()
        self.cfg.script_gen.base_dir = Path(self.script_gen_dir.text()).expanduser()
        self.cfg.script_gen.workspace_dir = Path(self.workspace_dir.text()).expanduser()
        self.cfg.voice_clone.recording_target_seconds = float(self.recording_target.value())

        self.cfg.script_gen.default_provider = self.provider_combo.currentText()
        translation = self.translation_combo.currentText()
        self.cfg.script_gen.translation_provider = translation if translation != "(use default)" else None
        for p, edit in self.model_inputs.items():
            self.cfg.script_gen.models[p] = edit.text()

        self.cfg.voice_clone.voice_settings = {
            "stability": float(self.stability.value()),
            "similarity_boost": float(self.similarity.value()),
            "speed": float(self.speed.value()),
        }
        return self.cfg
