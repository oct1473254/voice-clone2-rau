"""Pre-show health checks for ``hamlet-ai doctor`` and the GUI doctor panel.

``run_checks(cfg)`` returns a :class:`DoctorReport` of individual
:class:`CheckResult`s. Every check is best-effort and never raises — failures
become ``warn``/``error`` results. External dependencies (the ElevenLabs client,
LLM connection tester, and audio device probe) are injectable so the suite can
exercise the logic without hitting the network or a microphone.

Exit-code mapping (used by the CLI): all ``ok`` → 0, any ``warn`` → 1, any
``error`` → 2.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable

from hamlet_ai.config import AppConfig

OK = "ok"
WARN = "warn"
ERROR = "error"


@dataclass
class CheckResult:
    name: str
    status: str  # OK | WARN | ERROR
    detail: str = ""


@dataclass
class DoctorReport:
    results: list[CheckResult] = field(default_factory=list)

    def add(self, name: str, status: str, detail: str = "") -> None:
        self.results.append(CheckResult(name, status, detail))

    @property
    def exit_code(self) -> int:
        if any(r.status == ERROR for r in self.results):
            return 2
        if any(r.status == WARN for r in self.results):
            return 1
        return 0


# ---------- individual checks ---------------------------------------------

def _check_dry_run(cfg: AppConfig, report: DoctorReport) -> None:
    report.add("DRY_RUN", OK, "ON (no API calls)" if cfg.dry_run else "OFF (live API)")


def _check_elevenlabs(cfg: AppConfig, report: DoctorReport, client_factory) -> None:
    if not cfg.elevenlabs_api_key:
        status = WARN if cfg.dry_run else ERROR
        report.add("ElevenLabs key", status, "ELEVENLABS_API_KEY not set")
        return
    if cfg.dry_run:
        report.add("ElevenLabs key", OK, "present (DRY_RUN — not contacting API)")
        return
    if client_factory is None:
        report.add("ElevenLabs key", OK, "present")
        return
    try:
        client = client_factory(cfg)
        voices = client.list_voices()
        report.add("ElevenLabs API", OK, f"list_voices returned {len(voices)} voice(s)")
    except Exception as e:  # noqa: BLE001
        report.add("ElevenLabs API", WARN, f"list_voices failed: {e}")


def _check_providers(cfg: AppConfig, report: DoctorReport, connection_tester) -> None:
    if connection_tester is None:
        return
    for provider in ("anthropic", "openai", "ollama"):
        try:
            ok, message = connection_tester(provider, cfg)
        except Exception as e:  # noqa: BLE001
            ok, message = False, str(e)
        report.add(f"LLM: {provider}", OK if ok else WARN, message)


def _check_write_access(cfg: AppConfig, report: DoctorReport) -> None:
    targets = {
        "VOICE-CLONE/RUNS": cfg.voice_clone.runs_dir,
        "VOICE-CLONE/LINES": cfg.voice_clone.lines_dir,
        "LLM-H": cfg.script_gen.base_dir,
    }
    for label, path in targets.items():
        try:
            path.mkdir(parents=True, exist_ok=True)
            probe = path / ".doctor_write_test"
            probe.write_text("ok", encoding="utf-8")
            probe.unlink()
            report.add(f"Write access: {label}", OK, str(path))
        except Exception as e:  # noqa: BLE001
            report.add(f"Write access: {label}", ERROR, f"{path}: {e}")


def _check_clone_txt(cfg: AppConfig, report: DoctorReport) -> None:
    script = cfg.voice_clone.script_file
    if not script.is_file():
        report.add("clone.txt", ERROR, f"missing: {script}")
        return
    try:
        from hamlet_ai.core.voice_clone.pipeline import parse_script

        lines = parse_script(script, log_fn=lambda *_: None)
    except Exception as e:  # noqa: BLE001
        report.add("clone.txt", ERROR, f"parse failed: {e}")
        return
    if not lines:
        report.add("clone.txt", WARN, "parsed but contains no cue lines")
        return
    names = ", ".join(name for name, _ in lines[:3])
    report.add("clone.txt", OK, f"{len(lines)} cue(s): {names}…")


def _check_qlab_files(cfg: AppConfig, report: DoctorReport) -> None:
    lines_dir = cfg.voice_clone.lines_dir
    ghosts = sorted(lines_dir.glob("ghost_*.mp3")) if lines_dir.is_dir() else []
    if ghosts:
        report.add("QLab files", OK, f"{len(ghosts)} ghost_*.mp3 present in LINES/")
    else:
        report.add("QLab files", WARN, "no ghost_*.mp3 in LINES/ yet")


def _check_stale_samples(cfg: AppConfig, report: DoctorReport) -> None:
    sample_dir = cfg.voice_clone.sample_dir
    stale = (
        [f for f in sample_dir.iterdir() if f.is_file() and not f.name.startswith(".")]
        if sample_dir.is_dir()
        else []
    )
    if stale:
        report.add("Stale samples", WARN, f"{len(stale)} file(s) left in legacy SAMPLE/")
    else:
        report.add("Stale samples", OK, "SAMPLE/ is clean")


def _check_expired_voices(cfg: AppConfig, report: DoctorReport, now: datetime | None) -> None:
    from hamlet_ai.core.voice_clone.voice_library import VoiceLibrary, _is_expired

    now = now or datetime.now(timezone.utc)
    lib = VoiceLibrary(cfg.voice_clone.voice_library_path)
    expired = [
        e
        for e in lib.load()
        if not e.remote_deleted
        and e.retention_policy == "delete_after_show"
        and _is_expired(e, now, cfg.retention)
    ]
    if expired:
        report.add(
            "Retention sweep",
            WARN,
            f"{len(expired)} clone(s) past delete_after_show TTL still present",
        )
    else:
        report.add("Retention sweep", OK, "no expired clones pending")


def _check_audio_devices(cfg: AppConfig, report: DoctorReport, audio_probe) -> None:
    if audio_probe is None:
        return
    try:
        devices = audio_probe()
    except Exception as e:  # noqa: BLE001
        report.add("Audio input", WARN, f"could not enumerate devices: {e}")
        return
    if devices:
        report.add("Audio input", OK, f"{len(devices)} input device(s)")
    else:
        report.add("Audio input", WARN, "no audio input devices found")


# ---------- orchestration --------------------------------------------------

def _default_client_factory(cfg: AppConfig):
    from hamlet_ai.core.elevenlabs import ElevenLabsClient

    return ElevenLabsClient(
        api_key=cfg.elevenlabs_api_key, timeout=cfg.voice_clone.api_timeout_seconds
    )


def _default_connection_tester(provider: str, cfg: AppConfig):
    from hamlet_ai.core.script_gen.llm import test_connection

    return test_connection(provider, cfg)


def _default_audio_probe():
    from hamlet_ai.core.audio.recorder import AudioRecorder

    return AudioRecorder.list_input_devices()


# Sentinel: distinguishes "use the real default probe" from None ("skip this probe").
_DEFAULT = object()


def run_checks(
    cfg: AppConfig,
    *,
    client_factory: Callable | None = _DEFAULT,
    connection_tester: Callable | None = _DEFAULT,
    audio_probe: Callable | None = _DEFAULT,
    now: datetime | None = None,
) -> DoctorReport:
    # Resolve sentinels via module globals at call time so tests can monkeypatch
    # the default probes; an explicit None means "skip that probe".
    if client_factory is _DEFAULT:
        client_factory = _default_client_factory
    if connection_tester is _DEFAULT:
        connection_tester = _default_connection_tester
    if audio_probe is _DEFAULT:
        audio_probe = _default_audio_probe

    report = DoctorReport()
    _check_dry_run(cfg, report)
    _check_elevenlabs(cfg, report, client_factory)
    _check_providers(cfg, report, connection_tester)
    _check_write_access(cfg, report)
    _check_clone_txt(cfg, report)
    _check_qlab_files(cfg, report)
    _check_stale_samples(cfg, report)
    _check_expired_voices(cfg, report, now)
    _check_audio_devices(cfg, report, audio_probe)
    return report


# ---------- rendering ------------------------------------------------------

_ICONS = {OK: "✅", WARN: "⚠️ ", ERROR: "❌"}


def format_report(report: DoctorReport) -> str:
    lines = ["🩺 hamlet-ai doctor", "=" * 40]
    for r in report.results:
        icon = _ICONS.get(r.status, "?")
        lines.append(f"{icon} {r.name}: {r.detail}")
    lines.append("=" * 40)
    summary = {OK: 0, WARN: 0, ERROR: 0}
    for r in report.results:
        summary[r.status] = summary.get(r.status, 0) + 1
    lines.append(
        f"{summary[OK]} ok, {summary[WARN]} warning(s), {summary[ERROR]} error(s)"
    )
    return "\n".join(lines)
