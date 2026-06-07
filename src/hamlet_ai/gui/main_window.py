"""Main window: top tabs for Script Gen + Voice Clone, bottom log dock, toolbar.

Tabs are added as placeholder widgets in this step; concrete UIs land in later
steps. This file is the steady framework — it owns the AppConfig, exposes a
shared LogPane to every child, and gives the operator a single Settings entry.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QCheckBox,
    QDockWidget,
    QLabel,
    QMainWindow,
    QTabWidget,
    QToolBar,
    QWidget,
)

from hamlet_ai.config import AppConfig, save_config
from hamlet_ai.gui.settings_dialog import SettingsDialog
from hamlet_ai.gui.widgets.log_pane import LogPane


class MainWindow(QMainWindow):
    cfg_changed = Signal()

    def __init__(self, cfg: AppConfig, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("Hamlet.AI")
        self.resize(1100, 720)
        self.cfg = cfg

        self.log_pane = LogPane(self)
        self.log_dock = QDockWidget("Log", self)
        self.log_dock.setObjectName("LogDock")
        self.log_dock.setWidget(self.log_pane)
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, self.log_dock)

        self.tabs = QTabWidget(self)
        self.setCentralWidget(self.tabs)
        # Placeholder tabs — replaced in subsequent steps.
        self._script_gen_placeholder = QLabel("Script Generation — wired in Step 13/14")
        self._script_gen_placeholder.setAlignment(Qt.AlignCenter)
        self._voice_clone_placeholder = QLabel("Voice Clone — wired in Step 11/12")
        self._voice_clone_placeholder.setAlignment(Qt.AlignCenter)
        self.tabs.addTab(self._script_gen_placeholder, "Script Generation")
        self.tabs.addTab(self._voice_clone_placeholder, "Voice Clone")

        self._build_toolbar()

    # ---------- Toolbar ----------
    def _build_toolbar(self) -> None:
        toolbar = QToolBar("Main", self)
        toolbar.setObjectName("MainToolbar")
        self.addToolBar(toolbar)

        self.dry_run_box = QCheckBox("DRY_RUN")
        self.dry_run_box.setToolTip("Skip ElevenLabs API calls; placeholders only.")
        self.dry_run_box.setChecked(self.cfg.dry_run)
        self.dry_run_box.toggled.connect(self._on_dry_run_toggled)
        toolbar.addWidget(self.dry_run_box)

        toolbar.addSeparator()

        self.api_status_label = QLabel(self._api_status_text())
        toolbar.addWidget(self.api_status_label)

        toolbar.addSeparator()
        settings_action = QAction("Settings…", self)
        settings_action.triggered.connect(self.open_settings)
        toolbar.addAction(settings_action)

    def _api_status_text(self) -> str:
        ok = []
        warn = []
        for name, key in (
            ("ElevenLabs", self.cfg.elevenlabs_api_key),
            ("Anthropic", self.cfg.anthropic_api_key),
            ("OpenAI", self.cfg.openai_api_key),
        ):
            (ok if key else warn).append(name)
        ok_part = f"✅ {', '.join(ok)}" if ok else ""
        warn_part = f"⚠️  Missing: {', '.join(warn)}" if warn else ""
        return f"   {ok_part}   {warn_part}".strip()

    # ---------- Slots ----------
    def _on_dry_run_toggled(self, checked: bool) -> None:
        self.cfg.dry_run = checked
        self.log_pane.append_message(f"DRY_RUN {'on' if checked else 'off'}")
        self.cfg_changed.emit()

    def open_settings(self) -> int:
        dlg = SettingsDialog(self.cfg, parent=self)
        result = dlg.exec()
        if result == SettingsDialog.Accepted:
            self.cfg = dlg.apply_to_cfg()
            self.dry_run_box.setChecked(self.cfg.dry_run)
            self.api_status_label.setText(self._api_status_text())
            try:
                save_config(self.cfg)
                self.log_pane.append_message("Settings saved.")
            except OSError as e:
                self.log_pane.append_message(f"Failed to save settings: {e}")
            self.cfg_changed.emit()
        return result

    # ---------- Worker wiring helper ----------
    def wire_worker_logging(self, worker) -> None:
        """Connect a worker's ``log`` signal to the shared log pane."""
        worker.log.connect(self.log_pane.append_message)
        if hasattr(worker, "failed"):
            worker.failed.connect(lambda msg: self.log_pane.append_message(f"❌ {msg}"))
