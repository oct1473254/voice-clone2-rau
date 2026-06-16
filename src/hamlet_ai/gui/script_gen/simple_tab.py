"""One-page Script Generation tab.

A small form — the two extra characters (Ophelia/Horatio by default) and an
optional setting — plus a big **Generate Scene** button that runs the whole
pipeline in one background pass: generate the German ghost-scene → split →
translate to English (for review) → TTS the German lines → copy to the Desktop
layout. The creative brief itself is fixed (see
``core.script_gen.prompt.construct_prompt``).

Once generation finishes, the full scene is shown to the operator for review —
**German first** (what will be voiced) then its **English translation** — so the
text can be checked before/while audio is produced.

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
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
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

        heading = QLabel("Generate the Hamlet ghost scene (German)")
        heading.setObjectName("sgHeading")
        layout.addWidget(heading)

        subtitle = QLabel(
            "A Pulitzer-style reimagining of Hamlet's ghost scene for 2026, "
            "generated in German. Hamlet and the Ghost are always present; name "
            "the two other characters and (optionally) a setting."
        )
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        self.character_one_edit = QLineEdit()
        self.character_one_edit.setText("Ophelia")
        form.addRow("Character 1", self.character_one_edit)
        self.character_two_edit = QLineEdit()
        self.character_two_edit.setText("Horatio")
        form.addRow("Character 2", self.character_two_edit)
        self.setting_edit = QLineEdit()
        self.setting_edit.setPlaceholderText("optional — set in, or mention… (blank = the playwright chooses)")
        form.addRow("Setting", self.setting_edit)

        self.provider_combo = QComboBox()
        for p in ("anthropic", "openai", "ollama"):
            self.provider_combo.addItem(p)
        self.provider_combo.setCurrentText(cfg.script_gen.default_provider)
        form.addRow("LLM provider", self.provider_combo)
        layout.addLayout(form)

        opts_row = QHBoxLayout()
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

        # ---- Review panes: German (performed) beside English (translation) ----
        # Side by side so the operator can follow along in both languages at once.
        review_row = QHBoxLayout()

        german_col = QVBoxLayout()
        german_col.addWidget(QLabel("German scene (performed — this is what gets voiced):"))
        self.german_view = QPlainTextEdit()
        self.german_view.setReadOnly(True)
        self.german_view.setPlaceholderText("The generated German scene will appear here.")
        german_col.addWidget(self.german_view, stretch=1)
        review_row.addLayout(german_col, stretch=1)

        english_col = QVBoxLayout()
        english_col.addWidget(QLabel("English translation (for review only):"))
        self.english_view = QPlainTextEdit()
        self.english_view.setReadOnly(True)
        self.english_view.setPlaceholderText("An English translation will appear here.")
        english_col.addWidget(self.english_view, stretch=1)
        review_row.addLayout(english_col, stretch=1)

        layout.addLayout(review_row, stretch=1)

    # ---------- helpers ----------
    def collect_params(self) -> ScriptGenParams:
        return ScriptGenParams(
            character_one=self.character_one_edit.text().strip(),
            character_two=self.character_two_edit.text().strip(),
            setting=self.setting_edit.text().strip(),
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

        self.german_view.clear()
        self.english_view.clear()

        worker = ScriptGenPipelineWorker(
            cfg,
            params,
            translate=True,  # always produce an English translation for review
            do_tts=self.tts_box.isChecked(),
        )
        worker.scene_ready.connect(self._on_scene_ready)
        worker.progress.connect(self._on_progress)
        worker.finished.connect(self._on_finished)
        worker.failed.connect(self._on_failed)

        self._set_busy(True)
        self.progress.setVisible(True)
        self.progress.setRange(0, 0)  # indeterminate until TTS reports counts
        self.status_label.setText("Working… see the log for details.")
        self._start_worker(worker)

    @Slot(str, str)
    def _on_scene_ready(self, german: str, english: str) -> None:
        self.german_view.setPlainText(german)
        self.english_view.setPlainText(english or "(no English translation available)")

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
