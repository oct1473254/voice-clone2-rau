"""One-page Script Generation tab + its end-to-end pipeline worker."""
from __future__ import annotations

import pytest

from hamlet_ai.config import AppConfig, ScriptGenSettings, VoiceCloneSettings
from hamlet_ai.gui import workers as workers_mod
from hamlet_ai.gui.script_gen.simple_tab import ScriptGenPanel
from hamlet_ai.gui.workers import ScriptGenPipelineWorker
from hamlet_ai.core.script_gen.prompt import ScriptGenParams


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


# ---------- Panel --------------------------------------------------------

def test_panel_warns_and_does_not_start_when_empty(qtbot, cfg):
    started: list = []
    panel = ScriptGenPanel(lambda: cfg, started.append)
    qtbot.addWidget(panel)
    panel._on_generate()
    assert started == []
    assert "⚠️" in panel.status_label.text()


def test_panel_starts_worker_with_options_when_valid(qtbot, cfg):
    started: list = []
    panel = ScriptGenPanel(lambda: cfg, started.append)
    qtbot.addWidget(panel)
    panel.play_edit.setText("Hamlet")
    panel.scene_edit.setText("ending")
    panel.character_edit.setText("GHOST")
    panel.include_edit.setText("a skull")
    panel.style_edit.setText("eerie")
    panel.provider_combo.setCurrentText("openai")
    panel.translate_box.setChecked(False)
    panel.tts_box.setChecked(True)

    panel._on_generate()

    assert len(started) == 1
    worker = started[0]
    assert isinstance(worker, ScriptGenPipelineWorker)
    assert worker.translate is False and worker.do_tts is True
    assert cfg.script_gen.default_provider == "openai"
    assert not panel.generate_btn.isEnabled()  # busy until finished


# ---------- Pipeline worker (dry run) ------------------------------------

def test_pipeline_worker_runs_end_to_end_dry_run(qtbot, cfg, monkeypatch):
    monkeypatch.setattr(
        workers_mod,
        "llm_generate",
        lambda *a, **k: "HAMLET: To be, or not to be.\nGHOST: Mark me well.",
    )
    params = ScriptGenParams(
        play_name="Hamlet",
        scene_name="ending",
        character_count=2,
        character_name="GHOST",
        include="a skull",
        style="eerie",
    )
    worker = ScriptGenPipelineWorker(cfg, params, translate=False, do_tts=True)
    finished: list = []
    worker.finished.connect(finished.append)
    worker.run()  # synchronous in-test; no QThread needed

    assert finished == [cfg.script_gen.base_dir]
    assert (cfg.script_gen.workspace_dir / "english_scene.txt").exists()
    # TTS (dry run) produced files copied into the Desktop Audio layout.
    audio_dir = cfg.script_gen.base_dir / "Audio"
    assert audio_dir.is_dir()
    assert any(audio_dir.iterdir())
