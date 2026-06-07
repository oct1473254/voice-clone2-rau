"""GUI tests for the Voice Library tab (Step 13 enhancements)."""
from __future__ import annotations

import pytest

from hamlet_ai.config import AppConfig, ScriptGenSettings, VoiceCloneSettings
from hamlet_ai.core.voice_clone.voice_library import VoiceEntry, VoiceLibrary
from hamlet_ai.gui.voice_clone.voice_library_tab import VoiceLibraryTab


@pytest.fixture(autouse=True)
def _no_modal(monkeypatch):
    """Neutralize blocking message boxes so headless tests don't hang."""
    from PySide6.QtWidgets import QMessageBox

    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: QMessageBox.StandardButton.Ok)
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: QMessageBox.StandardButton.Ok)


@pytest.fixture
def cfg(tmp_path) -> AppConfig:
    return AppConfig(
        voice_clone=VoiceCloneSettings(base_dir=tmp_path / "VOICE-CLONE"),
        script_gen=ScriptGenSettings(base_dir=tmp_path / "LLM-H", workspace_dir=tmp_path / "ws"),
        dry_run=True,
        elevenlabs_api_key="k",
    )


class _FakeClient:
    def __init__(self):
        self.deleted = []

    def delete_voice(self, voice_id):
        self.deleted.append(voice_id)
        return True


def _seed(cfg, **kw):
    lib = VoiceLibrary(cfg.voice_clone.voice_library_path)
    lib.add(VoiceEntry.new("v1", "Burt", "/t/v1.mp3", "v1.mp3", **kw))
    return lib


def test_model_shows_consent_and_retention_columns(qtbot, cfg):
    _seed(cfg, consent_confirmed=True, retention_policy="ephemeral")
    tab = VoiceLibraryTab(cfg)
    qtbot.addWidget(tab)
    assert "Consent" in tab.model.HEADERS
    assert "Retention" in tab.model.HEADERS
    # Row 0 consent column shows the check.
    from PySide6.QtCore import Qt

    consent_col = tab.model.HEADERS.index("Consent")
    idx = tab.model.index(0, consent_col)
    assert tab.model.data(idx, Qt.DisplayRole) == "✓"


def test_delete_remote_calls_client(qtbot, cfg):
    _seed(cfg)
    client = _FakeClient()
    tab = VoiceLibraryTab(cfg, client_factory=lambda: client)
    qtbot.addWidget(tab)
    tab.view.selectRow(0)
    tab._on_delete_remote()
    assert client.deleted == ["v1"]
    assert tab.library.get("v1") is None


def test_mark_ephemeral_updates_entry(qtbot, cfg):
    _seed(cfg, retention_policy="keep")
    tab = VoiceLibraryTab(cfg)
    qtbot.addWidget(tab)
    tab.view.selectRow(0)
    tab._on_mark_ephemeral()
    assert tab.library.get("v1").retention_policy == "ephemeral"


def test_sweep_removes_ephemeral(qtbot, cfg):
    _seed(cfg, retention_policy="ephemeral")
    client = _FakeClient()
    tab = VoiceLibraryTab(cfg, client_factory=lambda: client)
    qtbot.addWidget(tab)
    tab._on_sweep()
    assert tab.library.get("v1") is None
    assert client.deleted == ["v1"]
