"""Step 9: QObject workers expose log/progress/finished/failed via Qt signals.

Each test runs the worker synchronously by calling ``.run()`` on the test
thread, then verifies that the right signals fired with the right payloads.
``qtbot.waitSignal`` is used where a thread-crossing wait is meaningful.
"""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from PySide6.QtCore import QThread

from hamlet_ai.config import AppConfig, ScriptGenSettings, VoiceCloneSettings
from hamlet_ai.core.script_gen.line_splitter import ScriptLine
from hamlet_ai.core.script_gen.llm import LLMClients
from hamlet_ai.core.script_gen.prompt import ScriptGenParams
from hamlet_ai.gui import workers


@pytest.fixture
def worker_cfg(tmp_path) -> AppConfig:
    cfg = AppConfig(
        voice_clone=VoiceCloneSettings(
            base_dir=tmp_path / "VOICE-CLONE",
            clone_poll_interval=0.0,
            clone_timeout=1.0,
        ),
        script_gen=ScriptGenSettings(
            base_dir=tmp_path / "LLM-H",
            workspace_dir=tmp_path / "workspace",
        ),
        dry_run=True,
        elevenlabs_api_key="test",
        anthropic_api_key="test",
        openai_api_key="test",
    )
    for d in (
        cfg.voice_clone.sample_dir,
        cfg.voice_clone.lines_dir,
        cfg.voice_clone.archive_dir,
        cfg.voice_clone.adhoc_dir,
        cfg.voice_clone.script_file.parent,
        cfg.script_gen.base_dir,
        cfg.script_gen.workspace_dir,
    ):
        d.mkdir(parents=True, exist_ok=True)
    return cfg


def _sample(cfg: AppConfig) -> Path:
    p = cfg.voice_clone.sample_dir / "vol.mp3"
    p.write_bytes(b"FAKE")
    return p


# ---------- CloneWorker ---------------------------------------------------

def test_clone_worker_emits_finished_with_voice_id(qtbot, worker_cfg):
    _sample(worker_cfg)
    w = workers.CloneWorker(worker_cfg)
    with qtbot.waitSignal(w.finished, timeout=2000) as blocker:
        w.run()
    assert blocker.args == ["dry_run_voice_id_12345"]


def test_clone_worker_emits_failed_on_missing_sample(qtbot, worker_cfg):
    w = workers.CloneWorker(worker_cfg)
    with qtbot.waitSignal(w.failed, timeout=2000) as blocker:
        w.run()
    assert "audio file" in blocker.args[0].lower() or "sample" in blocker.args[0].lower()


def test_clone_worker_snapshots_cfg_at_construction(qtbot, worker_cfg):
    _sample(worker_cfg)
    w = workers.CloneWorker(worker_cfg)
    # Mutate the *original* cfg after construction
    worker_cfg.dry_run = False
    with qtbot.waitSignal(w.finished, timeout=2000):
        w.run()  # snapshot should still be dry_run=True


def test_clone_worker_runs_in_qthread(qtbot, worker_cfg):
    """End-to-end with a real QThread to verify signals cross threads."""
    _sample(worker_cfg)
    w = workers.CloneWorker(worker_cfg)
    thread = QThread()
    w.moveToThread(thread)
    thread.started.connect(w.run)
    w.finished.connect(thread.quit)
    with qtbot.waitSignal(thread.finished, timeout=3000):
        thread.start()
    assert not thread.isRunning()


# ---------- SynthesizeWorker ---------------------------------------------

def test_synthesize_worker_emits_progress_and_finished(qtbot, worker_cfg):
    lines = [("a.mp3", "Alpha"), ("b.mp3", "Beta"), ("c.mp3", "Gamma")]
    w = workers.SynthesizeWorker(worker_cfg, "vid", lines)
    progress: list[tuple[int, int]] = []
    line_done: list[tuple[str, Path]] = []
    w.progress.connect(lambda d, t: progress.append((d, t)))
    w.line_done.connect(lambda fn, p: line_done.append((fn, p)))
    with qtbot.waitSignal(w.finished, timeout=2000):
        w.run()
    assert progress == [(1, 3), (2, 3), (3, 3)]
    assert [fn for fn, _ in line_done] == ["a.mp3", "b.mp3", "c.mp3"]


# ---------- AdHocTTSWorker -----------------------------------------------

def test_adhoc_tts_worker_writes_to_adhoc_dir(qtbot, worker_cfg):
    w = workers.AdHocTTSWorker(worker_cfg, "vid", "Ad-hoc text", "adhoc_test.mp3")
    with qtbot.waitSignal(w.finished, timeout=2000) as blocker:
        w.run()
    out = blocker.args[0]
    assert out.parent == worker_cfg.voice_clone.adhoc_dir
    assert out.is_file()


# ---------- LLMGenerationWorker ------------------------------------------

def test_llm_generation_worker_uses_clients_and_emits_text(qtbot, worker_cfg):
    worker_cfg.script_gen.default_provider = "anthropic"

    class StubAnthropic:
        def messages_create(self, **_):
            return SimpleNamespace(content=[SimpleNamespace(text="HAMLET: Hi.")])

    params = ScriptGenParams("Ophelia", "Horatio")
    w = workers.LLMGenerationWorker(worker_cfg, params, clients=LLMClients(anthropic_factory=lambda _: StubAnthropic()))
    with qtbot.waitSignal(w.finished, timeout=2000) as blocker:
        w.run()
    assert blocker.args == ["HAMLET: Hi."]


def test_llm_generation_worker_emits_failed_on_sdk_error(qtbot, worker_cfg):
    class Broken:
        def messages_create(self, **_):
            raise RuntimeError("network down")

    params = ScriptGenParams("Ophelia", "Horatio")
    w = workers.LLMGenerationWorker(worker_cfg, params, clients=LLMClients(anthropic_factory=lambda _: Broken()))
    with qtbot.waitSignal(w.failed, timeout=2000) as blocker:
        w.run()
    assert "network down" in blocker.args[0]


# ---------- TranslationWorker -------------------------------------------

def test_translation_worker_emits_translated_text(qtbot, worker_cfg):
    worker_cfg.script_gen.default_provider = "anthropic"

    class StubAnthropic:
        def messages_create(self, **_):
            return SimpleNamespace(content=[SimpleNamespace(text="Sein oder Nichtsein.")])

    w = workers.TranslationWorker(worker_cfg, "To be or not to be.", clients=LLMClients(anthropic_factory=lambda _: StubAnthropic()))
    with qtbot.waitSignal(w.finished, timeout=2000) as blocker:
        w.run()
    assert blocker.args == ["Sein oder Nichtsein."]


# ---------- SplitterWorker ----------------------------------------------

def test_splitter_worker_emits_parsed_script(qtbot, worker_cfg):
    w = workers.SplitterWorker(worker_cfg, "HAMLET: Hi.\nGERTRUDE: Hello.")
    with qtbot.waitSignal(w.finished, timeout=2000) as blocker:
        w.run()
    parsed = blocker.args[0]
    assert len(parsed.lines) == 2
    assert parsed.characters == ["GERTRUDE", "HAMLET"]


# ---------- ScriptGenTTSWorker ------------------------------------------

def test_script_gen_tts_worker_progress_and_files(qtbot, worker_cfg, tmp_path):
    lines = [
        ScriptLine(1, "HAMLET", "First"),
        ScriptLine(2, "GERTRUDE", "Second"),
    ]
    out_dir = tmp_path / "output"
    out_dir.mkdir()
    w = workers.ScriptGenTTSWorker(
        worker_cfg, lines, voice_resolver=lambda line: f"voice-{line.character}", output_dir=out_dir
    )
    progress: list[tuple[int, int]] = []
    w.progress.connect(lambda d, t: progress.append((d, t)))
    with qtbot.waitSignal(w.finished, timeout=2000):
        w.run()
    assert progress == [(1, 2), (2, 2)]
    assert (out_dir / "001-HAMLET.mp3").is_file()
    assert (out_dir / "002-GERTRUDE.mp3").is_file()


# ---------- RunShowWorker -----------------------------------------------

def test_run_show_worker_completes_dry_run(qtbot, worker_cfg, fake_clone_txt_for_worker):
    from hamlet_ai.consent import new_consent

    _sample(worker_cfg)
    w = workers.RunShowWorker(worker_cfg, consent=new_consent("vol", "keep"))
    with qtbot.waitSignal(w.finished, timeout=3000):
        w.run()
    assert (worker_cfg.voice_clone.lines_dir / "ghost_00_sample.mp3").is_file()


@pytest.fixture
def fake_clone_txt_for_worker(worker_cfg) -> Path:
    p = worker_cfg.voice_clone.script_file
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("ghost_00_sample.mp3\nHi.\n\nghost_01.mp3\nHello.\n", encoding="utf-8")
    return p


# ---------- DoctorWorker --------------------------------------------------

def test_doctor_worker_emits_report(qtbot, worker_cfg, fake_clone_txt_for_worker, monkeypatch):
    import hamlet_ai.doctor as doctor_mod

    # Keep it hermetic — no network / microphone.
    monkeypatch.setattr(doctor_mod, "_default_client_factory", lambda c: None)
    monkeypatch.setattr(doctor_mod, "_default_connection_tester", lambda p, c: (True, "ok"))
    monkeypatch.setattr(doctor_mod, "_default_audio_probe", lambda: [(0, "Mic")])

    w = workers.DoctorWorker(worker_cfg)
    received = {}
    w.finished.connect(lambda report: received.setdefault("report", report))
    with qtbot.waitSignal(w.finished, timeout=3000):
        w.run()
    assert received["report"].results  # produced a report with checks
