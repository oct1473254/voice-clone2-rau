#!/usr/bin/env bash
# Cross-platform launcher for the Hamlet.AI GUI (macOS + Linux).
#
# Run it from a terminal (`scripts/hamlet-ai.sh`) or double-click it in your file
# manager. On first run it installs native audio + GUI libraries (Linux only),
# creates the project virtualenv, installs the GUI extras, loads `.env`, and
# launches `hamlet-ai gui`. macOS users can keep double-clicking
# `scripts/hamlet-ai.command`, which just calls this script.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_DIR"

# --- Native system libraries (Linux only) ----------------------------------
# macOS bundles these (PortAudio via the sounddevice wheel; MP3 playback via
# AVFoundation; native windowing). On Linux they are separate system packages:
#   * PortAudio  → sounddevice / microphone recording
#   * GStreamer libav + good plugins → QtMultimedia MP3 playback of cue files
#   * xcb-cursor → Qt's xcb platform plugin (the GUI aborts without it)
# Installed once, on first run. Set HAMLET_SKIP_SYSDEPS=1 to skip.
install_linux_sys_deps() {
    if [ "${HAMLET_SKIP_SYSDEPS:-0}" = "1" ]; then
        return 0
    fi

    local need_portaudio=0 need_gstreamer=0 need_xcb_cursor=0
    if ! ldconfig -p 2>/dev/null | grep -qi 'libportaudio'; then
        need_portaudio=1
    fi
    if ! gst-inspect-1.0 avdec_mp3 >/dev/null 2>&1 \
       && ! gst-inspect-1.0 mpg123audiodec >/dev/null 2>&1; then
        need_gstreamer=1
    fi
    if ! ldconfig -p 2>/dev/null | grep -qi 'libxcb-cursor'; then
        need_xcb_cursor=1
    fi
    if [ "$need_portaudio" -eq 0 ] && [ "$need_gstreamer" -eq 0 ] \
       && [ "$need_xcb_cursor" -eq 0 ]; then
        return 0
    fi

    local pkgs=()
    [ "$need_portaudio" -eq 1 ] && pkgs+=(libportaudio2)
    [ "$need_gstreamer" -eq 1 ] && pkgs+=(gstreamer1.0-libav gstreamer1.0-plugins-good)
    [ "$need_xcb_cursor" -eq 1 ] && pkgs+=(libxcb-cursor0)

    if ! command -v apt-get >/dev/null 2>&1; then
        echo "⚠️  Missing system libraries: ${pkgs[*]}"
        echo "    apt-get not found — install them with your package manager, then re-run."
        echo "    (Run 'hamlet-ai doctor' for the exact command for your distro.)"
        return 0
    fi

    echo "Installing system libraries (${pkgs[*]}) — may prompt for your sudo password…"
    sudo apt-get update -qq
    sudo apt-get install -y "${pkgs[@]}"
}

if [ "$(uname -s)" = "Linux" ]; then
    install_linux_sys_deps
fi

# --- Python environment -----------------------------------------------------
if [ ! -d ".venv" ]; then
    echo "First run — creating virtual environment and installing Hamlet.AI…"
    python3 -m venv .venv
    ./.venv/bin/python -m pip install --upgrade pip
    ./.venv/bin/pip install -e ".[gui,audio,providers]"
fi

# shellcheck disable=SC1091
source .venv/bin/activate

# Load ELEVENLABS_API_KEY / provider keys from .env if present.
if [ -f ".env" ]; then
    set -a
    # shellcheck disable=SC1091
    source .env
    set +a
fi

# --- Settings/state location ------------------------------------------------
# The app stores settings.json (saved prompt, model choice, etc.) here. The
# default ~/.config/hamlet-ai can be root-owned — and thus unwritable — on
# machines where the app was ever started with sudo, which surfaces as
# "permission denied" when saving. Keep state beside the app instead, where the
# launching user can always write. Override by exporting HAMLET_AI_CONFIG_DIR.
export HAMLET_AI_CONFIG_DIR="${HAMLET_AI_CONFIG_DIR:-$REPO_DIR/.hamlet-state}"
mkdir -p "$HAMLET_AI_CONFIG_DIR"
# One-time carry-over of an existing ~/.config settings file (prompt, etc.).
legacy_settings="$HOME/.config/hamlet-ai/settings.json"
if [ ! -f "$HAMLET_AI_CONFIG_DIR/settings.json" ] && [ -f "$legacy_settings" ]; then
    cp "$legacy_settings" "$HAMLET_AI_CONFIG_DIR/settings.json" 2>/dev/null || true
fi

exec hamlet-ai gui
