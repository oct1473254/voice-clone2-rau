"""Step 10: SettingsDialog reads cfg, edits round-trip, never persists API keys."""
from __future__ import annotations


import pytest

from hamlet_ai.config import AppConfig, ScriptGenSettings, VoiceCloneSettings, save_config
from hamlet_ai.gui.settings_dialog import SettingsDialog


@pytest.fixture
def setting_cfg(tmp_path) -> AppConfig:
    return AppConfig(
        voice_clone=VoiceCloneSettings(base_dir=tmp_path / "VOICE-CLONE", recording_target_seconds=90.0),
        script_gen=ScriptGenSettings(
            base_dir=tmp_path / "LLM-H",
            workspace_dir=tmp_path / "workspace",
            default_provider="anthropic",
        ),
        dry_run=True,
        elevenlabs_api_key="el-key",
        anthropic_api_key="an-key",
    )


def test_dialog_constructs_with_three_tabs(qtbot, setting_cfg):
    dlg = SettingsDialog(setting_cfg)
    qtbot.addWidget(dlg)
    assert dlg.tabs.count() == 3
    assert {dlg.tabs.tabText(i) for i in range(3)} == {"General", "LLM", "ElevenLabs"}


def test_dialog_reads_initial_values(qtbot, setting_cfg):
    dlg = SettingsDialog(setting_cfg)
    qtbot.addWidget(dlg)
    assert dlg.dry_run_box.isChecked() is True
    assert dlg.provider_combo.currentText() == "anthropic"
    assert dlg.recording_target.value() == pytest.approx(90.0)
    assert dlg.model_inputs["anthropic"].text() == "claude-opus-4-8"


def test_apply_to_cfg_writes_back_changes(qtbot, setting_cfg):
    dlg = SettingsDialog(setting_cfg)
    qtbot.addWidget(dlg)
    dlg.dry_run_box.setChecked(False)
    dlg.recording_target.setValue(45.0)
    dlg.provider_combo.setCurrentText("openai")
    dlg.translation_combo.setCurrentText("ollama")
    dlg.model_inputs["openai"].setText("gpt-4o-mini")
    dlg.stability.setValue(0.4)
    cfg = dlg.apply_to_cfg()
    assert cfg.dry_run is False
    assert cfg.voice_clone.recording_target_seconds == pytest.approx(45.0)
    assert cfg.script_gen.default_provider == "openai"
    assert cfg.script_gen.translation_provider == "ollama"
    assert cfg.script_gen.models["openai"] == "gpt-4o-mini"
    assert cfg.voice_clone.voice_settings["stability"] == pytest.approx(0.4)


def test_save_config_never_persists_api_keys_when_invoked_from_dialog(qtbot, setting_cfg, tmp_path):
    dlg = SettingsDialog(setting_cfg)
    qtbot.addWidget(dlg)
    cfg = dlg.apply_to_cfg()
    settings_path = tmp_path / "settings.json"
    save_config(cfg, settings_path=settings_path)
    raw = settings_path.read_text()
    assert "el-key" not in raw
    assert "an-key" not in raw


def test_translation_combo_use_default_means_none(qtbot, setting_cfg):
    setting_cfg.script_gen.translation_provider = "openai"
    dlg = SettingsDialog(setting_cfg)
    qtbot.addWidget(dlg)
    dlg.translation_combo.setCurrentText("(use default)")
    cfg = dlg.apply_to_cfg()
    assert cfg.script_gen.translation_provider is None


def test_api_key_status_label_reflects_missing_key(qtbot, setting_cfg):
    setting_cfg.elevenlabs_api_key = None
    dlg = SettingsDialog(setting_cfg)
    qtbot.addWidget(dlg)
    el_tab = dlg.tabs.widget(2)
    from PySide6.QtWidgets import QLabel
    labels = [w.text() for w in el_tab.findChildren(QLabel)]
    assert any("NOT set" in t for t in labels)
