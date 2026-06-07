"""Step 10: MainWindow opens, hosts both tabs + a log pane, owns AppConfig."""
from __future__ import annotations

from pathlib import Path

import pytest

from hamlet_ai.config import AppConfig, ScriptGenSettings, VoiceCloneSettings
from hamlet_ai.gui.main_window import MainWindow


@pytest.fixture
def gui_cfg(tmp_path) -> AppConfig:
    return AppConfig(
        voice_clone=VoiceCloneSettings(base_dir=tmp_path / "VOICE-CLONE"),
        script_gen=ScriptGenSettings(
            base_dir=tmp_path / "LLM-H",
            workspace_dir=tmp_path / "workspace",
        ),
        dry_run=True,
        elevenlabs_api_key="el-key",
    )


def test_main_window_opens_with_two_top_tabs(qtbot, gui_cfg):
    w = MainWindow(gui_cfg)
    qtbot.addWidget(w)
    assert w.tabs.count() == 2
    assert w.tabs.tabText(0) == "Script Generation"
    assert w.tabs.tabText(1) == "Voice Clone"


def test_log_pane_appends_messages(qtbot, gui_cfg):
    w = MainWindow(gui_cfg)
    qtbot.addWidget(w)
    w.log_pane.append_message("hello")
    w.log_pane.append_message("world")
    text = w.log_pane.toPlainText()
    assert "hello" in text
    assert "world" in text


def test_log_pane_is_read_only(qtbot, gui_cfg):
    w = MainWindow(gui_cfg)
    qtbot.addWidget(w)
    assert w.log_pane.isReadOnly() is True


def test_toolbar_has_dry_run_and_api_status_and_settings(qtbot, gui_cfg):
    w = MainWindow(gui_cfg)
    qtbot.addWidget(w)
    assert w.dry_run_box.isChecked() is True
    assert "ElevenLabs" in w.api_status_label.text()


def test_dry_run_toggle_updates_cfg_and_logs(qtbot, gui_cfg):
    w = MainWindow(gui_cfg)
    qtbot.addWidget(w)
    captured: list[bool] = []
    w.cfg_changed.connect(lambda: captured.append(w.cfg.dry_run))
    w.dry_run_box.setChecked(False)
    assert w.cfg.dry_run is False
    assert captured == [False]
    assert "off" in w.log_pane.toPlainText()


def test_wire_worker_logging_forwards_log_and_failed(qtbot, gui_cfg):
    from PySide6.QtCore import QObject, Signal

    class FakeWorker(QObject):
        log = Signal(str)
        failed = Signal(str)

    w = MainWindow(gui_cfg)
    qtbot.addWidget(w)
    fake = FakeWorker()
    w.wire_worker_logging(fake)
    fake.log.emit("step 1 done")
    fake.failed.emit("kaboom")
    text = w.log_pane.toPlainText()
    assert "step 1 done" in text
    assert "❌" in text
    assert "kaboom" in text


def test_api_status_warns_when_keys_missing(qtbot, gui_cfg):
    gui_cfg.elevenlabs_api_key = None
    gui_cfg.anthropic_api_key = None
    w = MainWindow(gui_cfg)
    qtbot.addWidget(w)
    assert "Missing" in w.api_status_label.text()
