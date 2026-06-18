"""Prompt tab: view/edit the scene-generation prompt as one persisted text box."""
from __future__ import annotations

import pytest

from hamlet_ai.config import AppConfig, ScriptGenSettings, VoiceCloneSettings
from hamlet_ai.core.script_gen.prompt import DEFAULT_PROMPT_TEMPLATE
from hamlet_ai.gui.script_gen.prompt_tab import PromptTab


@pytest.fixture
def cfg(tmp_path) -> AppConfig:
    return AppConfig(
        voice_clone=VoiceCloneSettings(base_dir=tmp_path / "VOICE-CLONE"),
        script_gen=ScriptGenSettings(
            base_dir=tmp_path / "LLM-H",
            workspace_dir=tmp_path / "ws",
        ),
        dry_run=True,
    )


def test_loads_default_prompt_when_no_override(qtbot, cfg):
    tab = PromptTab(lambda: cfg)
    qtbot.addWidget(tab)
    assert tab.editor.toPlainText() == DEFAULT_PROMPT_TEMPLATE


def test_loads_existing_custom_override(qtbot, cfg):
    cfg.script_gen.prompt_template = "MY CUSTOM {character_one} PROMPT"
    tab = PromptTab(lambda: cfg)
    qtbot.addWidget(tab)
    assert tab.editor.toPlainText() == "MY CUSTOM {character_one} PROMPT"


def test_save_persists_custom_text_and_calls_hook(qtbot, cfg):
    saved: list[bool] = []
    tab = PromptTab(lambda: cfg, on_save=lambda: saved.append(True))
    qtbot.addWidget(tab)
    tab.editor.setPlainText("A brand new prompt with {character_two}")
    tab._on_save_clicked()
    assert cfg.script_gen.prompt_template == "A brand new prompt with {character_two}"
    assert saved == [True]


def test_save_stores_none_when_text_matches_default(qtbot, cfg):
    cfg.script_gen.prompt_template = "stale custom value"
    tab = PromptTab(lambda: cfg)
    qtbot.addWidget(tab)
    tab.editor.setPlainText(DEFAULT_PROMPT_TEMPLATE)
    tab._on_save_clicked()
    assert cfg.script_gen.prompt_template is None


def test_reset_restores_default_in_editor(qtbot, cfg):
    cfg.script_gen.prompt_template = "something else"
    tab = PromptTab(lambda: cfg)
    qtbot.addWidget(tab)
    tab._on_reset()
    assert tab.editor.toPlainText() == DEFAULT_PROMPT_TEMPLATE


def test_set_locked_disables_editing(qtbot, cfg):
    tab = PromptTab(lambda: cfg)
    qtbot.addWidget(tab)
    tab.set_locked(True)
    assert tab.editor.isReadOnly()
    assert not tab.save_btn.isEnabled()
    tab.set_locked(False)
    assert not tab.editor.isReadOnly()
    assert tab.save_btn.isEnabled()
