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
    QPushButton,
    QStatusBar,
    QTabWidget,
    QToolBar,
    QWidget,
)

from hamlet_ai.config import AppConfig, save_config
from hamlet_ai.gui.settings_dialog import SettingsDialog
from hamlet_ai.gui.widgets.log_pane import LogPane
from hamlet_ai.gui.widgets.status_pill import StatusPill
from hamlet_ai.show_mode import FALLBACK_ACTIONS, is_locked


class MainWindow(QMainWindow):
    cfg_changed = Signal()
    show_mode_changed = Signal(bool)

    def __init__(self, cfg: AppConfig, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("Hamlet.AI")
        self.resize(1100, 720)
        self.cfg = cfg
        self._el_tested_ok = False

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
        self._build_status_bar()
        self._apply_show_mode_locks()

    # ---------- Toolbar ----------
    def _build_toolbar(self) -> None:
        toolbar = QToolBar("Main", self)
        toolbar.setObjectName("MainToolbar")
        self.addToolBar(toolbar)

        self.show_mode_box = QCheckBox("SHOW MODE")
        self.show_mode_box.setToolTip("Lock risky controls during a live performance.")
        self.show_mode_box.setChecked(self.cfg.show_mode)
        self.show_mode_box.toggled.connect(self._on_show_mode_toggled)
        toolbar.addWidget(self.show_mode_box)

        toolbar.addSeparator()

        self.dry_run_box = QCheckBox("DRY_RUN")
        self.dry_run_box.setToolTip("Skip ElevenLabs API calls; placeholders only.")
        self.dry_run_box.setChecked(self.cfg.dry_run)
        self.dry_run_box.toggled.connect(self._on_dry_run_toggled)
        toolbar.addWidget(self.dry_run_box)

        toolbar.addSeparator()

        # Traffic-light ElevenLabs key indicator + legacy text status.
        self.key_indicator = QLabel()
        toolbar.addWidget(self.key_indicator)
        self.api_status_label = QLabel(self._api_status_text())
        toolbar.addWidget(self.api_status_label)
        self._refresh_key_indicator()

        toolbar.addSeparator()
        self.settings_action = QAction("Settings…", self)
        self.settings_action.triggered.connect(self.open_settings)
        toolbar.addAction(self.settings_action)

        self.doctor_action = QAction("Doctor", self)
        self.doctor_action.triggered.connect(self.run_doctor)
        toolbar.addAction(self.doctor_action)

    # ---------- Status bar (pills + fallbacks) ----------
    def _build_status_bar(self) -> None:
        bar = QStatusBar(self)
        self.setStatusBar(bar)

        self.status_pill = StatusPill(self)
        bar.addWidget(self.status_pill)
        self.set_status("dry_run" if self.cfg.dry_run else "ready")

        # Prominent fallback buttons (shown only in Show Mode).
        self.fallback_buttons: dict[str, QPushButton] = {}
        labels = {
            "restore_last_good": "Restore last good LINES/",
            "use_stock_ghost_voice": "Use stock Ghost voice",
            "regenerate_selected_line": "Regenerate selected line",
            "open_qlab_folder": "Open QLab folder",
        }
        for action in FALLBACK_ACTIONS:
            btn = QPushButton(labels.get(action, action))
            btn.setObjectName(f"fallback_{action}")
            btn.clicked.connect(lambda _=False, a=action: self.trigger_fallback(a))
            bar.addPermanentWidget(btn)
            self.fallback_buttons[action] = btn

    def set_status(self, state: str, text: str | None = None) -> None:
        self.status_pill.set_state(state, text)

    def trigger_fallback(self, action: str) -> None:
        """Handle a Show Mode fallback button. Each is a one-tap rescue."""
        self.log_pane.append_message(f"Fallback: {action}")
        if action == "restore_last_good":
            from hamlet_ai.core.voice_clone.pipeline import restore_last_good

            try:
                restored = restore_last_good(self.cfg, log_fn=self.log_pane.append_message)
                self.log_pane.append_message(f"Restored {len(restored)} file(s) to LINES/.")
                self.set_status("qlab_ready")
            except FileNotFoundError as e:
                self.log_pane.append_message(f"❌ {e}")
        elif action == "open_qlab_folder":
            self._open_in_file_manager(self.cfg.voice_clone.lines_dir)

    def _open_in_file_manager(self, path) -> None:
        import subprocess
        import sys

        path = str(path)
        try:
            if sys.platform == "darwin":
                subprocess.Popen(["open", path])
            elif sys.platform.startswith("win"):
                subprocess.Popen(["explorer", path])
            else:
                subprocess.Popen(["xdg-open", path])
        except Exception as e:  # noqa: BLE001
            self.log_pane.append_message(f"Could not open {path}: {e}")

    # ---------- Show Mode ----------
    def _on_show_mode_toggled(self, checked: bool) -> None:
        self.cfg.show_mode = checked
        self._apply_show_mode_locks()
        self.log_pane.append_message(f"Show Mode {'ON' if checked else 'off'}")
        self.show_mode_changed.emit(checked)
        self.cfg_changed.emit()

    def _apply_show_mode_locks(self) -> None:
        sm = self.cfg.show_mode
        # Lock risky controls.
        if hasattr(self, "settings_action"):
            self.settings_action.setEnabled(not is_locked("settings", sm))
        # Fallback buttons are only meaningful in Show Mode.
        for btn in getattr(self, "fallback_buttons", {}).values():
            btn.setVisible(sm)

    # ---------- Doctor ----------
    def run_doctor(self) -> "object":
        from hamlet_ai.doctor import format_report, run_checks

        report = run_checks(self.cfg)
        for line in format_report(report).splitlines():
            self.log_pane.append_message(line)
        # Promote the EL indicator to green if the API check passed.
        if any(r.name == "ElevenLabs API" and r.status == "ok" for r in report.results):
            self._el_tested_ok = True
            self._refresh_key_indicator()
        return report

    # ---------- Key indicator (traffic light) ----------
    def _refresh_key_indicator(self) -> None:
        if not self.cfg.elevenlabs_api_key:
            color, text = "#b71c1c", "● key: missing"  # red
        elif self._el_tested_ok:
            color, text = "#2e7d32", "● key: OK"  # green
        else:
            color, text = "#ef6c00", "● key: untested"  # yellow
        self.key_indicator.setText(text)
        self.key_indicator.setStyleSheet(f"color: {color}; font-weight: bold;")

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
            self._refresh_key_indicator()
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
