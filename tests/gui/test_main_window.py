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


# ---------- Step 11: Show Mode, status bar, Doctor, key indicator ----------

def test_toolbar_has_show_mode_and_doctor(qtbot, gui_cfg):
    w = MainWindow(gui_cfg)
    qtbot.addWidget(w)
    assert w.show_mode_box.isChecked() is False
    assert w.doctor_action.text() == "Doctor"


def test_show_mode_toggle_locks_settings_and_shows_fallbacks(qtbot, gui_cfg):
    w = MainWindow(gui_cfg)
    qtbot.addWidget(w)
    assert w.settings_action.isEnabled() is True
    assert w.fallback_buttons["restore_last_good"].isVisible() is False

    captured = []
    w.show_mode_changed.connect(captured.append)
    w.show_mode_box.setChecked(True)

    assert w.cfg.show_mode is True
    assert w.settings_action.isEnabled() is False  # locked
    assert captured == [True]


def test_status_pill_reflects_state(qtbot, gui_cfg):
    w = MainWindow(gui_cfg)
    qtbot.addWidget(w)
    w.set_status("recording")
    assert w.status_pill.state == "recording"


def test_key_indicator_red_when_missing(qtbot, gui_cfg):
    gui_cfg.elevenlabs_api_key = None
    w = MainWindow(gui_cfg)
    qtbot.addWidget(w)
    assert "missing" in w.key_indicator.text()


def test_key_indicator_yellow_when_present_untested(qtbot, gui_cfg):
    w = MainWindow(gui_cfg)
    qtbot.addWidget(w)
    assert "untested" in w.key_indicator.text()


def test_run_doctor_logs_report(qtbot, gui_cfg, monkeypatch):
    import hamlet_ai.doctor as doctor_mod

    monkeypatch.setattr(doctor_mod, "_default_client_factory", lambda c: None)
    monkeypatch.setattr(doctor_mod, "_default_connection_tester", lambda p, c: (True, "ok"))
    monkeypatch.setattr(doctor_mod, "_default_audio_probe", lambda: [(0, "Mic")])
    w = MainWindow(gui_cfg)
    qtbot.addWidget(w)
    report = w.run_doctor()
    assert report.results
    assert "hamlet-ai doctor" in w.log_pane.toPlainText()


def test_restore_last_good_fallback(qtbot, gui_cfg):
    # Seed an archive to restore from.
    archive = gui_cfg.voice_clone.archive_dir / "20240101_000000"
    archive.mkdir(parents=True)
    (archive / "ghost_00.mp3").write_bytes(b"x")
    w = MainWindow(gui_cfg)
    qtbot.addWidget(w)
    w.trigger_fallback("restore_last_good")
    assert (gui_cfg.voice_clone.lines_dir / "ghost_00.mp3").is_file()
