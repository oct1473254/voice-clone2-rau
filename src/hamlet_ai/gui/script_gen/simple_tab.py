"""One-page Script Generation tab.

A single form (play, scene, characters, style, …) plus a big **Generate Scene**
button that runs the whole pipeline — generate → split → translate → TTS →
copy to the Desktop layout — in one background pass. Progress and detailed log
lines stream to the shared log pane; this tab shows a compact status + progress
bar so the operator isn't forced to read the log.

The tab owns no threads. It builds a :class:`ScriptGenPipelineWorker` and hands
it to ``start_worker`` (supplied by MainWindow), which manages the QThread and
forwards log/failed signals to the shared pane.
"""
from __future__ import annotations

from typing import Callable

from PySide6.QtCore import Qt, Slot
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from hamlet_ai.config import AppConfig
from hamlet_ai.core.script_gen.prompt import ScriptGenParams
from hamlet_ai.gui.workers import ScriptGenPipelineWorker


class ScriptGenPanel(QWidget):
    def __init__(
        self,
        cfg_provider: Callable[[], AppConfig],
        start_worker: Callable[[object], None],
        provider_tester: Callable[[str, AppConfig], tuple[bool, str]] | None = None,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self._cfg_provider = cfg_provider
        self._start_worker = start_worker
        self._provider_tester = provider_tester
        cfg = cfg_provider()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(14)

        heading = QLabel("Generate a Shakespeare-style scene")
        heading.setObjectName("sgHeading")
        layout.addWidget(heading)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        self.play_edit = QLineEdit()
        self.play_edit.setPlaceholderText("e.g. Hamlet")
        form.addRow("Play", self.play_edit)
        self.scene_edit = QLineEdit()
        self.scene_edit.setPlaceholderText("e.g. Act II, Scene 1 — or 'ending'")
        form.addRow("Scene", self.scene_edit)
        self.count_spin = QSpinBox()
        self.count_spin.setRange(2, 4)
        form.addRow("Number of characters", self.count_spin)
        self.character_edit = QLineEdit()
        self.character_edit.setPlaceholderText("character to include, e.g. GHOST")
        form.addRow("Character to include", self.character_edit)
        self.include_edit = QLineEdit()
        self.include_edit.setPlaceholderText("a person, place, event, or thing")
        form.addRow("Incorporate", self.include_edit)
        self.style_edit = QLineEdit()
        self.style_edit.setPlaceholderText("e.g. eerie, comic, noir")
        form.addRow("Style", self.style_edit)

        self.provider_combo = QComboBox()
        for p in ("anthropic", "openai", "ollama"):
            self.provider_combo.addItem(p)
        self.provider_combo.setCurrentText(cfg.script_gen.default_provider)
        form.addRow("LLM provider", self.provider_combo)
        layout.addLayout(form)

        opts_row = QHBoxLayout()
        self.translate_box = QCheckBox("Translate to German")
        self.translate_box.setChecked(True)
        opts_row.addWidget(self.translate_box)
        self.tts_box = QCheckBox("Generate audio (TTS)")
        self.tts_box.setChecked(True)
        opts_row.addWidget(self.tts_box)
        opts_row.addStretch(1)
        self.test_btn = QPushButton("Test Connection")
        self.test_btn.clicked.connect(self._on_test_connection)
        opts_row.addWidget(self.test_btn)
        layout.addLayout(opts_row)

        self.generate_btn = QPushButton("Generate Scene")
        self.generate_btn.setObjectName("generateButton")
        self.generate_btn.setMinimumHeight(64)
        self.generate_btn.clicked.connect(self._on_generate)
        layout.addWidget(self.generate_btn)

        self.progress = QProgressBar()
        self.progress.setVisible(False)
        layout.addWidget(self.progress)

        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)
        layout.addStretch(1)

    # ---------- helpers ----------
    def collect_params(self) -> ScriptGenParams:
        return ScriptGenParams(
            play_name=self.play_edit.text().strip(),
            scene_name=self.scene_edit.text().strip(),
            character_count=self.count_spin.value(),
            character_name=self.character_edit.text().strip(),
            include=self.include_edit.text().strip(),
            style=self.style_edit.text().strip(),
        )

    def _set_busy(self, busy: bool) -> None:
        self.generate_btn.setEnabled(not busy)
        self.test_btn.setEnabled(not busy)
        self.generate_btn.setText("Generating…" if busy else "Generate Scene")

    # ---------- slots ----------
    @Slot()
    def _on_test_connection(self) -> None:
        cfg = self._cfg_provider()
        provider = self.provider_combo.currentText()
        tester = self._provider_tester
        if tester is None:
            from hamlet_ai.core.script_gen.llm import test_connection as tester
        try:
            ok, msg = tester(provider, cfg)
        except Exception as e:  # noqa: BLE001
            ok, msg = False, str(e)
        self.status_label.setText(("✅ " if ok else "⚠️ ") + msg)

    @Slot()
    def _on_generate(self) -> None:
        params = self.collect_params()
        errors = params.validate()
        if errors:
            self.status_label.setText("⚠️ " + "; ".join(errors))
            return

        cfg = self._cfg_provider()
        cfg.script_gen.default_provider = self.provider_combo.currentText()

        worker = ScriptGenPipelineWorker(
            cfg,
            params,
            translate=self.translate_box.isChecked(),
            do_tts=self.tts_box.isChecked(),
        )
        worker.progress.connect(self._on_progress)
        worker.finished.connect(self._on_finished)
        worker.failed.connect(self._on_failed)

        self._set_busy(True)
        self.progress.setVisible(True)
        self.progress.setRange(0, 0)  # indeterminate until TTS reports counts
        self.status_label.setText("Working… see the log for details.")
        self._start_worker(worker)

    @Slot(int, int)
    def _on_progress(self, done: int, total: int) -> None:
        self.progress.setRange(0, total)
        self.progress.setValue(done)

    @Slot(object)
    def _on_finished(self, desktop_root) -> None:
        self._set_busy(False)
        self.progress.setVisible(False)
        self.status_label.setText(f"✅ Done. Files written to {desktop_root}")

    @Slot(str)
    def _on_failed(self, message: str) -> None:
        self._set_busy(False)
        self.progress.setVisible(False)
        self.status_label.setText(f"❌ {message}")
