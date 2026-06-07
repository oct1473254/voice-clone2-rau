"""Microphone recorder built on sounddevice + soundfile.

``AudioRecorder`` is a ``QObject`` so it emits Qt signals: ``level_changed``
(RMS, 0..1), ``duration_changed`` (seconds elapsed), ``finished`` (path of
written WAV), and ``error`` (string message).

The stream callback runs on sounddevice's audio thread; the callback only
appends to a numpy buffer and emits signals. Qt's ``QueuedConnection`` semantics
handle hopping the signal to the GUI thread safely.

Tests inject mocked ``sounddevice.InputStream`` and ``soundfile.write`` so the
recorder can be exercised headless.
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Callable

import numpy as np
from PySide6.QtCore import QObject, Signal

try:
    import sounddevice as sd
except OSError:  # pragma: no cover — sounddevice's loader may fail without PortAudio
    sd = None  # type: ignore[assignment]

import soundfile as sf


class AudioRecorder(QObject):
    level_changed = Signal(float)
    duration_changed = Signal(float)
    finished = Signal(object)  # Path
    error = Signal(str)

    def __init__(
        self,
        samplerate: int = 48000,
        channels: int = 1,
        device: int | None = None,
        parent: QObject | None = None,
    ):
        super().__init__(parent)
        self.samplerate = samplerate
        self.channels = channels
        self.device = device

        self._stream: Any | None = None
        self._buffers: list[np.ndarray] = []
        self._target_seconds: float | None = None
        self._start_time: float = 0.0
        self._output_path: Path | None = None
        self._auto_stop_requested = False

    @staticmethod
    def list_input_devices() -> list[tuple[int, str]]:
        """Return ``(index, name)`` for each available input device."""
        if sd is None:
            return []
        devices = sd.query_devices()
        out: list[tuple[int, str]] = []
        for idx, dev in enumerate(devices):
            if dev.get("max_input_channels", 0) > 0:
                out.append((idx, dev.get("name", f"Device {idx}")))
        return out

    @property
    def is_recording(self) -> bool:
        return self._stream is not None

    def start(self, output_path: Path, target_seconds: float | None = None) -> None:
        if self._stream is not None:
            raise RuntimeError("AudioRecorder already running.")
        if sd is None:
            raise RuntimeError("sounddevice is unavailable; cannot record audio.")
        self._buffers = []
        self._output_path = Path(output_path)
        self._target_seconds = target_seconds
        self._auto_stop_requested = False
        self._start_time = time.monotonic()

        try:
            self._stream = sd.InputStream(
                samplerate=self.samplerate,
                channels=self.channels,
                device=self.device,
                callback=self._on_audio,
            )
            self._stream.start()
        except Exception as e:  # noqa: BLE001
            self._stream = None
            self.error.emit(f"Failed to open input stream: {e}")
            raise

    def stop(self) -> Path | None:
        if self._stream is None:
            return None
        try:
            self._stream.stop()
            self._stream.close()
        except Exception:  # noqa: BLE001 — best effort
            pass
        self._stream = None
        return self._flush_to_disk()

    def _flush_to_disk(self) -> Path | None:
        if self._output_path is None:
            return None
        if not self._buffers:
            audio = np.zeros((0, self.channels), dtype=np.float32)
        else:
            audio = np.concatenate(self._buffers, axis=0)
        self._output_path.parent.mkdir(parents=True, exist_ok=True)
        sf.write(str(self._output_path), audio, self.samplerate, subtype="PCM_16")
        out = self._output_path
        self.finished.emit(out)
        return out

    def _on_audio(self, indata: np.ndarray, frames: int, time_info: Any, status: Any) -> None:
        """sounddevice callback (audio thread)."""
        # Make a copy — sounddevice reuses the buffer
        chunk = np.array(indata, copy=True)
        self._buffers.append(chunk)
        rms = float(np.sqrt(np.mean(np.square(chunk)))) if chunk.size else 0.0
        elapsed = time.monotonic() - self._start_time
        self.level_changed.emit(min(rms, 1.0))
        self.duration_changed.emit(elapsed)
        if (
            not self._auto_stop_requested
            and self._target_seconds is not None
            and elapsed >= self._target_seconds
        ):
            self._auto_stop_requested = True
            # Defer stop to the main thread so the callback returns cleanly.
            from PySide6.QtCore import QMetaObject, Qt
            QMetaObject.invokeMethod(self, "stop", Qt.QueuedConnection)
