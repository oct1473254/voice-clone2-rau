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

def test_panel_prefills_ophelia_and_horatio(qtbot, cfg):
    panel = ScriptGenPanel(lambda: cfg, lambda _w: None)
    qtbot.addWidget(panel)
    assert panel.character_one_edit.text() == "Ophelia"
    assert panel.character_two_edit.text() == "Horatio"


def test_panel_warns_and_does_not_start_when_character_blank(qtbot, cfg):
    started: list = []
    panel = ScriptGenPanel(lambda: cfg, started.append)
    qtbot.addWidget(panel)
    panel.character_one_edit.setText("")  # blank a required field
    panel._on_generate()
    assert started == []
    assert "⚠️" in panel.status_label.text()


def test_panel_starts_worker_with_options_when_valid(qtbot, cfg):
    started: list = []
    panel = ScriptGenPanel(lambda: cfg, started.append)
    qtbot.addWidget(panel)
    panel.character_one_edit.setText("Marcellus")
    panel.character_two_edit.setText("Bernardo")
    panel.setting_edit.setText("a Berlin U-Bahn platform")
    panel.provider_combo.setCurrentText("openai")
    panel.tts_box.setChecked(True)

    panel._on_generate()

    assert len(started) == 1
    worker = started[0]
    assert isinstance(worker, ScriptGenPipelineWorker)
    assert worker.translate is True and worker.do_tts is True  # English always produced
    assert worker.params.character_one == "Marcellus"
    assert worker.params.setting == "a Berlin U-Bahn platform"
    assert cfg.script_gen.default_provider == "openai"
    assert not panel.generate_btn.isEnabled()  # busy until finished


# ---------- Pipeline worker (dry run) ------------------------------------

def test_pipeline_worker_runs_end_to_end_dry_run(qtbot, cfg, monkeypatch):
    # German scene out of the LLM; English produced by the (stubbed) translator.
    monkeypatch.setattr(
        workers_mod,
        "llm_generate",
        lambda *a, **k: "HAMLET: Sein oder Nichtsein.\nGEIST: Hör mir zu.",
    )
    monkeypatch.setattr(
        workers_mod,
        "translate_scene",
        lambda parsed, *a, **k: parsed,  # echo back; English text just needs to exist
    )
    params = ScriptGenParams(character_one="Ophelia", character_two="Horatio")
    worker = ScriptGenPipelineWorker(cfg, params, translate=True, do_tts=True)
    scenes: list = []
    finished: list = []
    worker.scene_ready.connect(lambda de, en: scenes.append((de, en)))
    worker.finished.connect(finished.append)
    worker.run()  # synchronous in-test; no QThread needed

    assert finished == [cfg.script_gen.base_dir]
    assert (cfg.script_gen.workspace_dir / "german_scene.txt").exists()
    # The German scene is surfaced for review (and English alongside it).
    assert scenes and "Sein oder Nichtsein" in scenes[0][0]
    # TTS (dry run) voiced the German lines into the Desktop Audio layout.
    audio_dir = cfg.script_gen.base_dir / "Audio"
    assert audio_dir.is_dir()
    assert any(audio_dir.iterdir())
