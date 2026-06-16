"""Unit tests for cross-platform native-dependency detection."""
from __future__ import annotations

import subprocess

import pytest

from hamlet_ai import platform_support as ps


def test_current_os_normalizes(monkeypatch):
    monkeypatch.setattr(ps.platform, "system", lambda: "Darwin")
    assert ps.current_os() == "macos"
    monkeypatch.setattr(ps.platform, "system", lambda: "Linux")
    assert ps.current_os() == "linux"
    monkeypatch.setattr(ps.platform, "system", lambda: "Windows")
    assert ps.current_os() == "windows"


def test_install_commands_none_off_linux(monkeypatch):
    monkeypatch.setattr(ps.platform, "system", lambda: "Darwin")
    assert ps.portaudio_install_command() is None
    assert ps.gstreamer_install_command() is None


def test_install_commands_apt(monkeypatch):
    monkeypatch.setattr(ps.platform, "system", lambda: "Linux")
    monkeypatch.setattr(ps.shutil, "which", lambda exe: "/usr/bin/apt-get" if exe == "apt-get" else None)
    assert ps.portaudio_install_command() == "sudo apt-get install -y libportaudio2"
    assert (
        ps.gstreamer_install_command()
        == "sudo apt-get install -y gstreamer1.0-libav gstreamer1.0-plugins-good"
    )


def test_install_commands_pacman(monkeypatch):
    monkeypatch.setattr(ps.platform, "system", lambda: "Linux")
    monkeypatch.setattr(ps.shutil, "which", lambda exe: "/usr/bin/pacman" if exe == "pacman" else None)
    assert ps.portaudio_install_command() == "sudo pacman -S --needed --noconfirm portaudio"


def test_install_command_none_when_no_known_manager(monkeypatch):
    monkeypatch.setattr(ps.platform, "system", lambda: "Linux")
    monkeypatch.setattr(ps.shutil, "which", lambda exe: None)
    assert ps.portaudio_install_command() is None


def test_probe_portaudio_missing(monkeypatch):
    def boom(name, *a, **k):
        if name == "sounddevice":
            raise OSError("PortAudio library not found")
        return __import__(name, *a, **k)

    monkeypatch.setattr(ps.platform, "system", lambda: "Linux")
    monkeypatch.setattr(ps.shutil, "which", lambda exe: "/usr/bin/apt-get" if exe == "apt-get" else None)
    monkeypatch.setattr("builtins.__import__", boom)
    status = ps.probe_portaudio()
    assert status.available is False
    assert "libportaudio2" in (status.fix_command or "")


def test_probe_portaudio_present(monkeypatch):
    import sys
    import types

    monkeypatch.setitem(sys.modules, "sounddevice", types.ModuleType("sounddevice"))
    status = ps.probe_portaudio()
    assert status.available is True
    assert status.fix_command is None


def test_probe_gstreamer_native_off_linux(monkeypatch):
    monkeypatch.setattr(ps.platform, "system", lambda: "Darwin")
    status = ps.probe_gstreamer_mp3()
    assert status.available is True


def test_probe_gstreamer_missing_tool(monkeypatch):
    monkeypatch.setattr(ps.platform, "system", lambda: "Linux")
    monkeypatch.setattr(ps.shutil, "which", lambda exe: None)
    status = ps.probe_gstreamer_mp3()
    assert status.available is False
    assert status.fix_command is None  # no package manager either


def test_probe_gstreamer_decoder_found(monkeypatch):
    monkeypatch.setattr(ps.platform, "system", lambda: "Linux")
    monkeypatch.setattr(ps.shutil, "which", lambda exe: "/usr/bin/" + exe)

    def fake_run(cmd, **kw):
        element = cmd[1]
        return subprocess.CompletedProcess(cmd, 0 if element == "avdec_mp3" else 1)

    monkeypatch.setattr(ps.subprocess, "run", fake_run)
    status = ps.probe_gstreamer_mp3()
    assert status.available is True
    assert "avdec_mp3" in status.detail


def test_probe_gstreamer_no_decoder(monkeypatch):
    monkeypatch.setattr(ps.platform, "system", lambda: "Linux")
    monkeypatch.setattr(ps.shutil, "which", lambda exe: "/usr/bin/" + exe)
    monkeypatch.setattr(
        ps.subprocess, "run", lambda cmd, **kw: subprocess.CompletedProcess(cmd, 1)
    )
    status = ps.probe_gstreamer_mp3()
    assert status.available is False
    assert "gstreamer1.0-libav" in (status.fix_command or "")


def test_probe_audio_deps_returns_both():
    deps = ps.probe_audio_deps()
    names = [d.name for d in deps]
    assert any("PortAudio" in n for n in names)
    assert any("MP3" in n for n in names)


def test_xcb_cursor_install_command_apt(monkeypatch):
    monkeypatch.setattr(ps.platform, "system", lambda: "Linux")
    monkeypatch.setattr(ps.shutil, "which", lambda exe: "/usr/bin/apt-get" if exe == "apt-get" else None)
    assert ps.xcb_cursor_install_command() == "sudo apt-get install -y libxcb-cursor0"


def test_xcb_cursor_install_command_none_off_linux(monkeypatch):
    monkeypatch.setattr(ps.platform, "system", lambda: "Darwin")
    assert ps.xcb_cursor_install_command() is None


def test_probe_qt_xcb_native_off_linux(monkeypatch):
    monkeypatch.setattr(ps.platform, "system", lambda: "Darwin")
    status = ps.probe_qt_xcb()
    assert status.available is True
    assert status.fix_command is None


def test_probe_qt_xcb_present(monkeypatch):
    monkeypatch.setattr(ps.platform, "system", lambda: "Linux")
    monkeypatch.setattr(ps.ctypes, "CDLL", lambda name: object())
    status = ps.probe_qt_xcb()
    assert status.available is True


def test_probe_qt_xcb_missing(monkeypatch):
    monkeypatch.setattr(ps.platform, "system", lambda: "Linux")
    monkeypatch.setattr(ps.shutil, "which", lambda exe: "/usr/bin/apt-get" if exe == "apt-get" else None)

    def boom(name):
        raise OSError(f"{name}: cannot open shared object file")

    monkeypatch.setattr(ps.ctypes, "CDLL", boom)
    status = ps.probe_qt_xcb()
    assert status.available is False
    assert "libxcb-cursor0" in (status.fix_command or "")


def test_probe_native_deps_includes_qt():
    deps = ps.probe_native_deps()
    names = [d.name for d in deps]
    assert any("PortAudio" in n for n in names)
    assert any("MP3" in n for n in names)
    assert any("xcb-cursor" in n for n in names)
