"""Audio playback via QMediaPlayer.

QMediaPlayer plays mp3 natively on macOS via AVFoundation and on Linux via
gstreamer, so we don't pull in extra codec dependencies. The wrapper normalizes
the signal set to plain Python types so test assertions don't depend on Qt
enum values.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, QUrl, Signal
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer


class AudioPlayer(QObject):
    state_changed = Signal(str)  # "playing" | "paused" | "stopped" | "error"
    position_changed = Signal(int)  # ms
    duration_changed = Signal(int)  # ms

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self._player = QMediaPlayer(self)
        self._audio_output = QAudioOutput(self)
        self._player.setAudioOutput(self._audio_output)
        self._player.playbackStateChanged.connect(self._on_state)
        self._player.positionChanged.connect(self.position_changed.emit)
        self._player.durationChanged.connect(self.duration_changed.emit)
        self._player.errorOccurred.connect(self._on_error)

    def play(self, path: Path) -> None:
        self._player.setSource(QUrl.fromLocalFile(str(path)))
        self._player.play()

    def pause(self) -> None:
        self._player.pause()

    def stop(self) -> None:
        self._player.stop()

    def seek(self, position_ms: int) -> None:
        self._player.setPosition(position_ms)

    def _on_state(self, state: Any) -> None:
        if state == QMediaPlayer.PlaybackState.PlayingState:
            self.state_changed.emit("playing")
        elif state == QMediaPlayer.PlaybackState.PausedState:
            self.state_changed.emit("paused")
        else:
            self.state_changed.emit("stopped")

    def _on_error(self, error: Any, message: str = "") -> None:
        if error == QMediaPlayer.Error.NoError:
            return
        self.state_changed.emit("error")
