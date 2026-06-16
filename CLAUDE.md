# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

**HAMLET.AI — Voice Clone System** for the live theatrical production *Wember / Wolf359*. A single Python script captures a volunteer's voice during performance, clones it via ElevenLabs Instant Voice Cloning, and generates pre-scripted audio lines into a QLab-watched folder — all in under two minutes.

## Cross-platform (macOS + Linux)

The app (the `hamlet_ai` package; `voiceclone2.py`/`Hamlet-gen5.py` are now CLI shims) runs identically on macOS and Linux. The Python stack — PySide6, sounddevice, QtMultimedia — is portable; the only OS difference is three **native** libraries that macOS bundles but Linux installs separately:

- **PortAudio** (`libportaudio2`) — sounddevice backend for recording.
- **GStreamer MP3 decoder** (`gstreamer1.0-libav`, `gstreamer1.0-plugins-good`) — QtMultimedia MP3 playback.
- **xcb-cursor** (`libxcb-cursor0`) — Qt's X11 (`xcb`) platform plugin; without it the GUI aborts at startup ("Could not load the Qt platform plugin 'xcb'"). Linux/X11 only — Wayland uses the `wayland` plugin.

`src/hamlet_ai/platform_support.py` probes each and returns the per-distro install command; `doctor` surfaces any gap as a WARN with that command (via `probe_native_deps()`). The launcher `scripts/hamlet-ai.sh` auto-installs them on Linux first run (macOS uses `scripts/hamlet-ai.command`, which delegates to the `.sh`). When touching audio, windowing, or launchers, keep both OSes working and add a `platform_support` probe rather than hardcoding a path.

## Running the Script

```bash
# Set up (one-time)
python3 -m venv .venv
source .venv/bin/activate
pip install requests python-dotenv

# Run
python voiceclone2.py
```

Requires a `.env` file in the project root:
```
ELEVENLABS_API_KEY=your_api_key_here
```

## Configuration (top of voiceclone2.py)

| Variable | Default | Purpose |
|---|---|---|
| `DRY_RUN` | `True` | Test without API calls; writes text placeholders instead of mp3s |
| `MODEL_ID` | `eleven_v3` | Swap to `eleven_multilingual_v2` if pause tags cause issues |
| `VOICE_SETTINGS` | stability 0.3, similarity 0.75, speed 1.2 | Controls delivery character |

**Set `DRY_RUN = False` before a real show run.**

## Architecture

`voiceclone2.py` is the entire codebase. It runs in three phases:

**Phase 1 — Concurrent** (`ThreadPoolExecutor`, 3 workers):
- `clone_voice()` — uploads `SAMPLE/` audio to ElevenLabs IVC, returns `voice_id`
- `cleanup()` — archives existing `LINES/` and `SAMPLE/` files to `ARCHIVE/<timestamp>/`
- `parse_script()` — reads `clone.txt`, returns `[(filename, text), ...]`

**Phase 2 — Sequential**: `wait_for_voice()` polls ElevenLabs until the cloned voice is confirmed ready (polls every 5s, timeout 120s)

**Phase 3 — Sequential**: `generate_lines()` iterates parsed script lines, calling `synthesize()` for each, writing mp3s to `LINES/`

## Folder Structure (all under `~/Desktop/VOICE-CLONE/`)

```
VOICE-CLONE/
├── SCRIPT/clone.txt   # Pre-written ghost lines — edit this for new scripts
├── SAMPLE/            # Drop one volunteer recording here before running
├── LINES/             # Output mp3s — QLab cues point here (filenames are fixed)
└── ARCHIVE/           # Auto-archived previous runs, named by timestamp
```

## clone.txt Format

Blocks separated by **two blank lines**. First line of each block is the output filename; remaining lines are the spoken text:

```
ghost_01_shakespeare.mp3
List, [pause] list, [pause] O, list!
If thou didst ever thy dear father love —
```

Pause tags (`[pause]`, `[long pause]`) are only interpreted by `eleven_v3`.

## ElevenLabs API

- **Clone endpoint**: `POST /v1/voices/add` (multipart, `files` + `name`/`description`)
- **Status check**: `GET /v1/voices/{voice_id}` — 200 = ready, 404 = not yet
- **TTS endpoint**: `POST /v1/text-to-speech/{voice_id}` — returns raw mp3 bytes
- Auth header: `xi-api-key`

`eleven_v3` supports pause tags and is the most expressive. `eleven_multilingual_v2` is the stable fallback (no pause tags). Requires Starter plan or above for IVC.
