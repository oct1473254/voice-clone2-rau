"""Cross-platform detection of the native libraries the app needs.

The Python layer (PySide6, sounddevice, QtMultimedia) is portable, but a few
native libraries differ by OS:

* **PortAudio** — sounddevice's backend (microphone recording). The macOS pip
  wheel bundles it; on Linux it must come from the system package
  ``libportaudio2`` (or distro equivalent).
* **A GStreamer MP3 decoder** — QtMultimedia plays the generated ``.mp3`` cue
  files through AVFoundation on macOS (built in) but through GStreamer on Linux,
  which needs ``gstreamer1.0-libav`` / ``-plugins-good`` for MP3.
* **xcb-cursor** — Qt's X11 (``xcb``) platform plugin needs
  ``libxcb-cursor.so.0`` since Qt 6.5; without it the GUI aborts at startup with
  "Could not load the Qt platform plugin 'xcb'". macOS/Windows use native
  windowing, and Wayland sessions use the ``wayland`` plugin, so this only bites
  Linux/X11.

This module probes each at runtime and, per OS + package manager, names the
install command that fixes a gap. ``doctor`` and the launcher use it so a
missing lib surfaces before a show, not during one.

Importing this module has no side effects and never raises.
"""
from __future__ import annotations

import ctypes
import platform
import shutil
import subprocess
from dataclasses import dataclass


def current_os() -> str:
    """Normalized OS name: ``"macos"``, ``"linux"``, ``"windows"``, or lowercase other."""
    system = platform.system()
    return {"Darwin": "macos", "Linux": "linux", "Windows": "windows"}.get(
        system, system.lower()
    )


@dataclass
class DepStatus:
    name: str  # human-readable label
    available: bool
    detail: str  # what the probe found
    fix_command: str | None = None  # shell command to install it, if missing


# ---------- package names per Linux package manager ------------------------

_PORTAUDIO_PKGS = {
    "apt-get": ["libportaudio2"],
    "dnf": ["portaudio"],
    "pacman": ["portaudio"],
    "zypper": ["libportaudio2"],
}

_GSTREAMER_PKGS = {
    "apt-get": ["gstreamer1.0-libav", "gstreamer1.0-plugins-good"],
    "dnf": ["gstreamer1-libav", "gstreamer1-plugins-good"],
    "pacman": ["gst-libav", "gst-plugins-good"],
    "zypper": ["gstreamer-plugins-libav", "gstreamer-plugins-good"],
}

_XCB_CURSOR_PKGS = {
    "apt-get": ["libxcb-cursor0"],
    "dnf": ["xcb-util-cursor"],
    "pacman": ["xcb-util-cursor"],
    "zypper": ["libxcb-cursor0"],
}

# How each manager installs a list of packages non-interactively.
_INSTALL_TEMPLATE = {
    "apt-get": "sudo apt-get install -y {pkgs}",
    "dnf": "sudo dnf install -y {pkgs}",
    "pacman": "sudo pacman -S --needed --noconfirm {pkgs}",
    "zypper": "sudo zypper install -y {pkgs}",
}


def _linux_pkg_manager() -> str | None:
    for mgr in ("apt-get", "dnf", "pacman", "zypper"):
        if shutil.which(mgr):
            return mgr
    return None


def _linux_install_command(pkgs_by_mgr: dict[str, list[str]]) -> str | None:
    mgr = _linux_pkg_manager()
    if mgr is None or mgr not in pkgs_by_mgr:
        return None
    return _INSTALL_TEMPLATE[mgr].format(pkgs=" ".join(pkgs_by_mgr[mgr]))


def portaudio_install_command() -> str | None:
    """Install command for PortAudio, or None if not applicable.

    Returns None on macOS/Windows (the pip wheel bundles PortAudio there).
    """
    if current_os() != "linux":
        return None
    return _linux_install_command(_PORTAUDIO_PKGS)


def gstreamer_install_command() -> str | None:
    """Install command for a GStreamer MP3 decoder, or None if not applicable.

    Returns None off Linux (native playback backends already decode MP3).
    """
    if current_os() != "linux":
        return None
    return _linux_install_command(_GSTREAMER_PKGS)


def xcb_cursor_install_command() -> str | None:
    """Install command for the Qt xcb plugin's xcb-cursor lib, or None.

    Returns None off Linux (macOS/Windows use native windowing).
    """
    if current_os() != "linux":
        return None
    return _linux_install_command(_XCB_CURSOR_PKGS)


# ---------- runtime probes -------------------------------------------------

def probe_portaudio() -> DepStatus:
    """Can sounddevice load its PortAudio backend?"""
    label = "Audio recording (PortAudio)"
    try:
        import sounddevice  # noqa: F401
    except OSError as e:  # sounddevice raises OSError when the C lib is missing
        return DepStatus(
            label,
            False,
            f"sounddevice could not load PortAudio ({e}); recording is unavailable",
            fix_command=portaudio_install_command(),
        )
    except Exception as e:  # noqa: BLE001 — any import failure means no recording
        return DepStatus(
            label,
            False,
            f"sounddevice import failed: {e}",
            fix_command=portaudio_install_command(),
        )
    return DepStatus(label, True, "sounddevice/PortAudio loaded")


def probe_gstreamer_mp3() -> DepStatus:
    """Can the platform's QtMultimedia backend decode MP3?

    macOS/Windows use native backends (always available). On Linux, QtMultimedia
    routes through GStreamer, so we check for an MP3 decoder element.
    """
    label = "Audio playback (MP3)"
    os_name = current_os()
    if os_name != "linux":
        return DepStatus(label, True, f"native playback backend on {os_name}")

    gst = shutil.which("gst-inspect-1.0")
    if not gst:
        return DepStatus(
            label,
            False,
            "GStreamer not installed (gst-inspect-1.0 not found); MP3 playback unavailable",
            fix_command=gstreamer_install_command(),
        )
    for element in ("avdec_mp3", "mpg123audiodec", "mad"):
        try:
            result = subprocess.run(
                [gst, element], capture_output=True, timeout=10
            )
        except (OSError, subprocess.SubprocessError):
            continue
        if result.returncode == 0:
            return DepStatus(label, True, f"GStreamer MP3 decoder present: {element}")
    return DepStatus(
        label,
        False,
        "no GStreamer MP3 decoder found; generated cue files will not play",
        fix_command=gstreamer_install_command(),
    )


def probe_qt_xcb() -> DepStatus:
    """Can Qt's X11 (xcb) platform plugin find its xcb-cursor dependency?

    Off Linux this is always satisfied (native windowing). On Linux the GUI
    aborts at startup if ``libxcb-cursor.so.0`` is missing and Qt falls back to
    the xcb plugin, so we check the lib is loadable.
    """
    label = "GUI windowing (Qt xcb-cursor)"
    if current_os() != "linux":
        return DepStatus(label, True, f"native windowing on {current_os()}")
    try:
        ctypes.CDLL("libxcb-cursor.so.0")
    except OSError:
        return DepStatus(
            label,
            False,
            "libxcb-cursor.so.0 not found; Qt xcb plugin fails to load and the GUI aborts",
            fix_command=xcb_cursor_install_command(),
        )
    return DepStatus(label, True, "libxcb-cursor.so.0 loaded")


def probe_audio_deps() -> list[DepStatus]:
    """Probe the native audio dependencies (PortAudio + GStreamer MP3)."""
    return [probe_portaudio(), probe_gstreamer_mp3()]


def probe_native_deps() -> list[DepStatus]:
    """Probe every native dependency (audio + GUI). Used by ``doctor``."""
    return [*probe_audio_deps(), probe_qt_xcb()]
