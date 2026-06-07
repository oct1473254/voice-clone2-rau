"""GUI tests for the Ad-hoc TTS tab."""
from __future__ import annotations

import pytest

from hamlet_ai.config import AppConfig, ScriptGenSettings, VoiceCloneSettings
from hamlet_ai.gui.voice_clone.adhoc_tts_tab import AdhocTtsTab


@pytest.fixture(autouse=True)
def _no_modal(monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: QMessageBox.StandardButton.Ok)
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: QMessageBox.StandardButton.Ok)


@pytest.fixture
def cfg(tmp_path) -> AppConfig:
    return AppConfig(
        voice_clone=VoiceCloneSettings(base_dir=tmp_path / "VOICE-CLONE"),
        script_gen=ScriptGenSettings(base_dir=tmp_path / "LLM-H", workspace_dir=tmp_path / "ws"),
        dry_run=True,
    )


def test_generate_writes_to_adhoc_dir(qtbot, cfg):
    cfg.voice_clone.adhoc_dir.mkdir(parents=True, exist_ok=True)
    tab = AdhocTtsTab(cfg)
    qtbot.addWidget(tab)
    tab.text_edit.setPlainText("An improvised ghostly whisper.")
    received = []
    tab.generated.connect(received.append)
    tab._on_generate()
    assert received, "generated signal not emitted"
    out = received[0]
    assert out.parent == cfg.voice_clone.adhoc_dir
    assert out.is_file()
    assert tab.play_btn.isEnabled()


def test_generate_requires_text(qtbot, cfg):
    tab = AdhocTtsTab(cfg)
    qtbot.addWidget(tab)
    tab.text_edit.setPlainText("   ")
    received = []
    tab.generated.connect(received.append)
    tab._on_generate()
    assert received == []
