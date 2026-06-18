"""Prompt tab: view and edit the scene-generation prompt as a single text box.

The operator rarely needs this, but it must be reachable: the whole prompt sent
to the LLM lives in one editable box. Edits persist to config
(``ScriptGenSettings.prompt_template``) and feed every generation path via
``construct_prompt``. The three placeholder tokens — ``{character_one}``,
``{character_two}`` and ``{setting_clause}`` — are filled per run from the
Script Generation tab; leaving them in keeps that per-show customisation working.

The box includes the technical formatting rules (``CHARACTER: dialogue``) the
downstream splitter and per-line TTS depend on, so a warning is shown and a
**Reset to default** button is always available to recover a bad edit.
"""
from __future__ import annotations

from typing import Callable

from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from hamlet_ai.config import AppConfig
from hamlet_ai.core.script_gen.prompt import DEFAULT_PROMPT_TEMPLATE


class PromptTab(QWidget):
    def __init__(
        self,
        cfg_provider: Callable[[], AppConfig],
        on_save: Callable[[], None] | None = None,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self._cfg_provider = cfg_provider
        # Persist hook (MainWindow saves config + logs). None → no-op for tests.
        self._on_save = on_save or (lambda: None)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(12)

        heading = QLabel("Scene-generation prompt")
        heading.setObjectName("sgHeading")
        layout.addWidget(heading)

        description = QLabel(
            "This is the full prompt sent to the LLM to generate the German ghost "
            "scene. You normally never need to touch it. The tokens "
            "<b>{character_one}</b>, <b>{character_two}</b> and "
            "<b>{setting_clause}</b> are filled in per run from the Script "
            "Generation tab — keep them to preserve that. The lower paragraph is "
            "technical formatting the line-splitter and audio depend on; if you "
            "remove it, generated scenes may fail to split or voice. Use "
            "<b>Reset to default</b> to restore the original prompt."
        )
        description.setWordWrap(True)
        layout.addWidget(description)

        self.editor = QPlainTextEdit()
        self.editor.setFont(QFont("Monospace"))
        self.editor.setPlaceholderText("The scene-generation prompt.")
        layout.addWidget(self.editor, stretch=1)

        button_row = QHBoxLayout()
        self.reset_btn = QPushButton("Reset to default")
        self.reset_btn.setToolTip("Restore the built-in prompt (then click Save to keep it).")
        self.reset_btn.clicked.connect(self._on_reset)
        button_row.addWidget(self.reset_btn)
        button_row.addStretch(1)
        self.save_btn = QPushButton("Save")
        self.save_btn.setObjectName("savePromptButton")
        self.save_btn.clicked.connect(self._on_save_clicked)
        button_row.addWidget(self.save_btn)
        layout.addLayout(button_row)

        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        self._load_from_cfg()

    # ---------- helpers ----------
    def _load_from_cfg(self) -> None:
        """Populate the editor from config (custom override, else the default)."""
        cfg = self._cfg_provider()
        self.editor.setPlainText(cfg.script_gen.prompt_template or DEFAULT_PROMPT_TEMPLATE)

    def set_locked(self, locked: bool) -> None:
        """Disable editing/saving (used while Show Mode locks risky controls)."""
        self.editor.setReadOnly(locked)
        self.save_btn.setEnabled(not locked)
        self.reset_btn.setEnabled(not locked)

    # ---------- slots ----------
    def _on_reset(self) -> None:
        self.editor.setPlainText(DEFAULT_PROMPT_TEMPLATE)
        self.status_label.setText("Restored the default prompt — click Save to keep it.")

    def _on_save_clicked(self) -> None:
        cfg = self._cfg_provider()
        text = self.editor.toPlainText()
        # Store None when the text matches the default so future default changes
        # propagate and the config stays free of redundant overrides.
        cfg.script_gen.prompt_template = None if text.strip() == DEFAULT_PROMPT_TEMPLATE.strip() else text
        self._on_save()
        is_default = cfg.script_gen.prompt_template is None
        self.status_label.setText(
            "Saved (using the default prompt)." if is_default else "Saved your custom prompt."
        )
