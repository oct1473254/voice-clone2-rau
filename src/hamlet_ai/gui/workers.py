"""QObject workers that wrap each long-running operation behind Qt signals.

Pattern: each worker is a plain ``QObject`` with ``log``, ``failed`` and one or
more operation-specific signals. Callers construct the worker, move it onto a
``QThread`` (``worker.moveToThread(thread); thread.started.connect(worker.run)``)
and connect signals to GUI slots. ``cfg`` is **snapshot at construction** via
``copy.deepcopy`` so mid-run toggles (e.g. flipping DRY_RUN) can't corrupt the
in-flight operation.

All workers swallow exceptions from the core into a ``failed(str)`` signal so
the QThread can exit cleanly even on errors.
"""
from __future__ import annotations

import copy
from pathlib import Path
from typing import Sequence

from PySide6.QtCore import QObject, Signal, Slot

from hamlet_ai.config import AppConfig
from hamlet_ai.core.script_gen.line_splitter import ScriptLine, split_script, write_split_files
from hamlet_ai.core.script_gen.llm import LLMClients, LLMProvider, generate as llm_generate
from hamlet_ai.core.script_gen.prompt import ScriptGenParams, construct_prompt
from hamlet_ai.core.script_gen.translation import (
    TranslationCountMismatch,
    translate as llm_translate,
    translate_scene,
)
from hamlet_ai.core.script_gen.tts import synthesize_line
from hamlet_ai.core.voice_clone import pipeline as vc_pipeline


# ---------- Base ----------------------------------------------------------

class _WorkerBase(QObject):
    log = Signal(str)
    failed = Signal(str)

    def __init__(self, cfg: AppConfig, parent: QObject | None = None):
        super().__init__(parent)
        self.cfg = copy.deepcopy(cfg)


# ---------- Voice Clone workers ------------------------------------------

class CloneWorker(_WorkerBase):
    finished = Signal(str)  # voice_id

    @Slot()
    def run(self) -> None:
        try:
            voice_id = vc_pipeline.clone_voice(self.cfg, log_fn=self.log.emit)
            voice_id = vc_pipeline.wait_for_voice(self.cfg, voice_id, log_fn=self.log.emit)
            self.finished.emit(voice_id)
        except Exception as e:  # noqa: BLE001
            self.failed.emit(str(e))


class SynthesizeWorker(_WorkerBase):
    progress = Signal(int, int)  # done, total
    line_done = Signal(str, object)  # filename, path
    finished = Signal()

    def __init__(self, cfg: AppConfig, voice_id: str, lines: Sequence[tuple[str, str]], parent: QObject | None = None):
        super().__init__(cfg, parent)
        self.voice_id = voice_id
        self.lines = list(lines)

    @Slot()
    def run(self) -> None:
        try:
            total = len(self.lines)
            for idx, (filename, text) in enumerate(self.lines, start=1):
                self.log.emit(f"[{idx}/{total}] {filename}")
                path = vc_pipeline.synthesize(
                    self.cfg, self.voice_id, text, filename, log_fn=self.log.emit
                )
                self.line_done.emit(filename, path)
                self.progress.emit(idx, total)
            self.finished.emit()
        except Exception as e:  # noqa: BLE001
            self.failed.emit(str(e))


class AdHocTTSWorker(_WorkerBase):
    finished = Signal(object)  # Path

    def __init__(self, cfg: AppConfig, voice_id: str, text: str, filename: str, parent: QObject | None = None):
        super().__init__(cfg, parent)
        self.voice_id = voice_id
        self.text = text
        self.filename = filename

    @Slot()
    def run(self) -> None:
        try:
            path = vc_pipeline.synthesize(
                self.cfg,
                self.voice_id,
                self.text,
                self.filename,
                log_fn=self.log.emit,
                output_dir=self.cfg.voice_clone.adhoc_dir,
            )
            self.finished.emit(path)
        except Exception as e:  # noqa: BLE001
            self.failed.emit(str(e))


class RunShowWorker(_WorkerBase):
    finished = Signal(object)  # RunFolder (carries .timings for the result panel)
    over_budget = Signal(object)  # timings dict, emitted only when the budget is blown

    def __init__(self, cfg: AppConfig, consent=None, parent: QObject | None = None):
        super().__init__(cfg, parent)
        self.consent = consent

    @Slot()
    def run(self) -> None:
        try:
            run = vc_pipeline.run_show(self.cfg, consent=self.consent, log_fn=self.log.emit)
            timings = getattr(run, "timings", {}) or {}
            if timings and not timings.get("within_budget", True):
                self.log.emit(
                    "⚠️  Clone exceeded the time budget — consider a fallback "
                    "(stock Ghost voice or Restore last good LINES/)."
                )
                self.over_budget.emit(timings)
            self.finished.emit(run)
        except Exception as e:  # noqa: BLE001
            self.failed.emit(str(e))


class DoctorWorker(_WorkerBase):
    """Runs the doctor checks off the GUI thread; emits the assembled report."""

    finished = Signal(object)  # DoctorReport

    @Slot()
    def run(self) -> None:
        try:
            from hamlet_ai.doctor import run_checks

            report = run_checks(self.cfg)
            for r in report.results:
                self.log.emit(f"{r.status.upper()}: {r.name} — {r.detail}")
            self.finished.emit(report)
        except Exception as e:  # noqa: BLE001
            self.failed.emit(str(e))


# ---------- Script Gen workers -------------------------------------------

class LLMGenerationWorker(_WorkerBase):
    finished = Signal(str)  # generated text

    def __init__(self, cfg: AppConfig, params: ScriptGenParams, clients: LLMClients | None = None, parent: QObject | None = None):
        super().__init__(cfg, parent)
        self.params = params
        self.clients = clients

    @Slot()
    def run(self) -> None:
        try:
            provider = LLMProvider(self.cfg.script_gen.default_provider)
            model = self.cfg.script_gen.models[provider.value]
            self.log.emit(f"Generating scene via {provider.value} ({model})...")
            prompt = construct_prompt(self.params, self.cfg.script_gen.prompt_template)
            text = llm_generate(
                prompt,
                provider,
                model,
                anthropic_api_key=self.cfg.anthropic_api_key,
                openai_api_key=self.cfg.openai_api_key,
                clients=self.clients,
            )
            self.finished.emit(text)
        except Exception as e:  # noqa: BLE001
            self.failed.emit(str(e))


class TranslationWorker(_WorkerBase):
    finished = Signal(str)

    def __init__(self, cfg: AppConfig, text: str, target_language: str = "German", clients: LLMClients | None = None, parent: QObject | None = None):
        super().__init__(cfg, parent)
        self.text = text
        self.target_language = target_language
        self.clients = clients

    @Slot()
    def run(self) -> None:
        try:
            self.log.emit(f"Translating to {self.target_language}...")
            out = llm_translate(self.text, self.cfg, target_language=self.target_language, clients=self.clients)
            self.finished.emit(out)
        except Exception as e:  # noqa: BLE001
            self.failed.emit(str(e))


class SplitterWorker(_WorkerBase):
    finished = Signal(object)  # ParsedScript

    def __init__(self, cfg: AppConfig, text: str, allowed: list[str] | None = None, parent: QObject | None = None):
        super().__init__(cfg, parent)
        self.text = text
        self.allowed = allowed

    @Slot()
    def run(self) -> None:
        try:
            self.log.emit("Splitting scene into lines...")
            parsed = split_script(self.text, allowed=self.allowed)
            self.log.emit(f"   ✅ {len(parsed.lines)} lines, {len(parsed.characters)} characters, {len(parsed.rejected)} rejected.")
            self.finished.emit(parsed)
        except Exception as e:  # noqa: BLE001
            self.failed.emit(str(e))


class ScriptGenPipelineWorker(_WorkerBase):
    """Run the whole one-page Script Gen flow in a single background pass.

    Generate (German) → split → (translate to English for review) → (TTS the
    German lines) → copy to the Desktop layout. German is the performed/voiced
    language; English is produced only so the operator can review what will be
    voiced. Emits ``log`` lines throughout, ``scene_ready(german, english)`` once
    both texts are known, ``progress`` for the per-line TTS step, and
    ``finished(desktop_root)`` on success. Per-line TTS failures are logged but
    never abort the run.
    """

    scene_ready = Signal(str, str)  # german_text, english_text (english may be "")
    progress = Signal(int, int)  # done, total (TTS phase)
    finished = Signal(object)  # Path — the Desktop output root

    def __init__(
        self,
        cfg: AppConfig,
        params: ScriptGenParams,
        *,
        translate: bool = True,
        do_tts: bool = True,
        clients: LLMClients | None = None,
        parent: QObject | None = None,
    ):
        super().__init__(cfg, parent)
        self.params = params
        self.translate = translate
        self.do_tts = do_tts
        self.clients = clients

    @Slot()
    def run(self) -> None:
        try:
            from hamlet_ai.config import ensure_dirs
            from hamlet_ai.core.script_gen.character_voices import CharacterVoiceMap
            from hamlet_ai.core.script_gen.export import copy_to_desktop

            ensure_dirs(self.cfg)
            workspace = self.cfg.script_gen.workspace_dir
            provider = LLMProvider(self.cfg.script_gen.default_provider)
            model = self.cfg.script_gen.models[provider.value]

            self.log.emit(f"🎭 Generating German scene via {provider.value} ({model})...")
            prompt = construct_prompt(self.params, self.cfg.script_gen.prompt_template)
            german = llm_generate(
                prompt,
                provider,
                model,
                anthropic_api_key=self.cfg.anthropic_api_key,
                openai_api_key=self.cfg.openai_api_key,
                clients=self.clients,
            )
            de_path = workspace / "german_scene.txt"
            de_path.parent.mkdir(parents=True, exist_ok=True)
            de_path.write_text(german, encoding="utf-8")
            self.log.emit(f"📝 German scene saved: {de_path}")

            parsed_de = split_script(german, allowed=self.params.allowed_characters())
            write_split_files(parsed_de, workspace, language="German")
            self.log.emit(f"🪓 Split {len(parsed_de.lines)} German lines.")

            english_text = ""
            if self.translate:
                self.log.emit("🌍 Translating to English for review (per line)...")
                try:
                    parsed_en = translate_scene(parsed_de, self.cfg, target_language="English", clients=self.clients)
                except TranslationCountMismatch as e:
                    self.log.emit(f"⚠️  English translation skipped (line count mismatch): {e}")
                    parsed_en = None
                except Exception as e:  # noqa: BLE001
                    self.log.emit(f"⚠️  English translation failed: {e}")
                    parsed_en = None
                if parsed_en is not None:
                    english_text = "\n".join(
                        f"{line.character}: {line.dialogue}" for line in parsed_en.lines
                    )
                    (workspace / "english_scene.txt").write_text(english_text, encoding="utf-8")
                    write_split_files(parsed_en, workspace, language="English")
                    self.log.emit(f"🪓 Split {len(parsed_en.lines)} English lines.")

            german_text = "\n".join(
                f"{line.character}: {line.dialogue}" for line in parsed_de.lines
            )
            self.scene_ready.emit(german_text, english_text)

            if self.do_tts:
                voice_map = CharacterVoiceMap(self.cfg.script_gen.character_voices_path)
                de_output = workspace / "valid_lines" / "German" / "output"
                de_output.mkdir(parents=True, exist_ok=True)
                total = len(parsed_de.lines)
                self.log.emit(f"🔊 Synthesizing {total} German lines...")
                for i, line in enumerate(parsed_de.lines, start=1):
                    voice_id = voice_map.resolve(line.character)
                    out = de_output / f"{line.line_number:03d}-{line.character}.mp3"
                    self.log.emit(f"[{i}/{total}] {out.name}")
                    try:
                        synthesize_line(self.cfg, line.dialogue, voice_id, out, log_fn=self.log.emit)
                    except Exception as e:  # noqa: BLE001 — keep going on per-line failure
                        self.log.emit(f"   ❌ Line {i}: {e}")
                    self.progress.emit(i, total)
                self.log.emit("🔊 TTS complete.")

            self.log.emit(f"📦 Copying to Desktop layout: {self.cfg.script_gen.base_dir}")
            copy_to_desktop(workspace, self.cfg.script_gen.base_dir, log_fn=self.log.emit)
            self.log.emit("🎭 Done.")
            self.finished.emit(self.cfg.script_gen.base_dir)
        except Exception as e:  # noqa: BLE001
            self.failed.emit(str(e))


class ScriptGenTTSWorker(_WorkerBase):
    progress = Signal(int, int)
    line_done = Signal(int, object)  # line_number, path
    finished = Signal()

    def __init__(
        self,
        cfg: AppConfig,
        lines: Sequence[ScriptLine],
        voice_resolver,  # Callable[[ScriptLine], str]
        output_dir: Path,
        parent: QObject | None = None,
    ):
        super().__init__(cfg, parent)
        self.lines = list(lines)
        self.voice_resolver = voice_resolver
        self.output_dir = output_dir

    @Slot()
    def run(self) -> None:
        try:
            total = len(self.lines)
            for idx, line in enumerate(self.lines, start=1):
                voice_id = self.voice_resolver(line)
                out = self.output_dir / f"{line.line_number:03d}-{line.character}.mp3"
                self.log.emit(f"[{idx}/{total}] {out.name} ({voice_id})")
                synthesize_line(self.cfg, line.dialogue, voice_id, out, log_fn=self.log.emit)
                self.line_done.emit(line.line_number, out)
                self.progress.emit(idx, total)
            self.finished.emit()
        except Exception as e:  # noqa: BLE001
            self.failed.emit(str(e))
