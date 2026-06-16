# HAMLET.AI

### Voice Clone + Shakespeare Scene Generator — Wember / Wolf359

A unified PySide6 application (with a headless CLI) for two live-theatre tools that share an ElevenLabs account:

1. **Voice Clone** — capture an audience volunteer's voice, clone it via ElevenLabs Instant Voice Cloning, and generate pre-scripted ghost lines into a QLab-watched folder, typically in under two minutes.
2. **Script Generation** — generate a Shakespeare-style scene with an LLM (Anthropic / OpenAI / Ollama), translate it per line into German, split it into per-character lines, and synthesize each line with a character→voice map.

Show-night safety is the priority: a sequential clone pipeline (no cleanup-during-clone race), explicit consent + retention for cloned voices, a Show Mode that locks risky controls, real playable DRY_RUN audio, redacted logs, and a `doctor` preflight.

---

## System Requirements

- **macOS** (developed on Mac Mini M4) or Linux (for headless/CI use)
- **Python 3.10+**
- **ElevenLabs account** with Instant Voice Cloning access (Starter plan or above)
- **QLab** for playback (configured separately)
- For Script Gen: at least one of an Anthropic key, an OpenAI key, or a local Ollama daemon

---

## Install

```bash
python3 -m venv .venv
source .venv/bin/activate

# Everything (GUI + audio + LLM providers + dev tools):
pip install -e ".[gui,audio,providers,dev]"

# Or a headless/core-only install (no GUI, no microphone):
pip install -e ".[core,providers]"
```

Create a `.env` in the project root (never commit it — it's in `.gitignore`):

```
ELEVENLABS_API_KEY=your_key_here
ANTHROPIC_API_KEY=your_key_here      # optional, for Script Gen
OPENAI_API_KEY=your_key_here         # optional, for Script Gen
```

API keys are read from the environment only — they are **never** written to `settings.json`.

### Supported entry points

| Command | Purpose |
|---|---|
| `hamlet-ai gui` | Launch the full application. |
| `hamlet-ai doctor` | Run the pre-show health checks (exit 0 = all green, 1 = warnings, 2 = errors). |
| `hamlet-ai voice-clone --i-consent` | Headless voice-clone run. |
| `hamlet-ai script-gen ...` | Headless scene generation. |

The legacy entry points still work: `python voiceclone2.py` and `python Hamlet-gen5.py` are thin shims that route through the CLI.

### macOS double-click launcher

`scripts/hamlet-ai.command` is a double-clickable launcher. On first run it creates the venv and installs the GUI extras, loads `.env`, and runs `hamlet-ai gui`. (A py2app `.app` bundle is possible but out of scope for v1.)

---

## First Run & Migration

On first launch the app inventories any existing `~/Desktop/VOICE-CLONE/` and `~/Desktop/LLM-H/` folders and writes a timestamped backup (`~/Desktop/VOICE-CLONE.backup-{ts}/`) before any write that could clobber existing artifacts. The inventory is recorded under `~/.config/hamlet-ai/`. Workspace folders are created if missing.

---

## Folder Structure

All voice-clone working folders live under `~/Desktop/VOICE-CLONE/`:

```
VOICE-CLONE/
├── SCRIPT/clone.txt     # Pre-written ghost lines with filenames (edit for new scripts)
├── SAMPLE/              # Drop ONE volunteer recording here before a run
├── RUNS/{timestamp}/    # Per-run workspace: sample copy, generated_lines, clone_metadata.json, run_log.txt
├── LINES/               # Output mp3s — QLab cues point here (filenames are fixed)
├── ADHOC/               # Ad-hoc TTS output
├── ARCHIVE/{timestamp}/ # Previous LINES/ runs, archived automatically
└── voice_library.json   # Recent clones with consent + retention metadata
```

Script-gen artifacts are copied (never moved) to `~/Desktop/LLM-H/`.

### Why RUNS/ exists

Every clone session gets its own `RUNS/{timestamp}/` folder. The volunteer sample is **copied** there and the clone reads from that copy, so cleanup can never move the sample out from under an in-flight clone. The previous `LINES/` is archived only **after** the new run succeeds; on failure `LINES/` is left untouched.

---

## clone.txt Format

At `VOICE-CLONE/SCRIPT/clone.txt`. Blocks are separated by **two blank lines**; the first line of each block is the output filename, the rest is the spoken text:

```
ghost_01_shakespeare.mp3
List, [pause] list, [pause] O, list!
If thou didst ever thy dear father love — [long pause]
Revenge his foul and most unnatural murder.


ghost_02_modern.mp3
Very bad murder, [pause] as all murders are...
```

Pause tags (`[pause]`, `[long pause]`) are interpreted only by the `eleven_v3` model.

---

## GUI Walkthrough

The main window has a persistent **status bar** (Ready / Recording / Cloning / Generating / QLab Ready / Failed / DRY_RUN / No API Key), a **toolbar** (Show Mode toggle, DRY_RUN toggle, traffic-light API-key indicator, Settings, Doctor), a central tabbed area, and a redacting **log pane** at the bottom.

### Voice Clone tab

- **Record** — consent dialog (first time per volunteer) → mic check → 3-2-1 prep → countdown to 0 with a level meter → auto-stop (target 90s, configurable) or manual Stop → Retry/Discard → **Clone This Recording** (runs the sequential pipeline with a retention choice).
- **Voice Library** — recent clones with Label, Voice ID, Created, Sample, Consent ✓, Retention, Remote-deleted. Buttons: Set Active, Play Sample, Rename, Delete (local), Delete (local + ElevenLabs), Mark Ephemeral, and **Delete expired clones now** (sweep).
- **Scripted Lines** — editable `clone.txt`, per-row Play, generate selected/all.
- **Ad-hoc** — type text, synthesize to `ADHOC/`.
- **Archive** — browse `ARCHIVE/{ts}/`, per-row Play, and **Restore last good LINES/** (the show-night rescue path).

The result panel reports the actual clone time against the **2-minute budget**; overruns surface fallback buttons (Use stock Ghost voice / Restore last good).

### Script Generation tab (stepper)

Input → Generate → Splitter → Translation (per line) → Voices → TTS → Export, with an edit checkpoint at each stage. Translation is **per line** and preserves each character label and line id; a count mismatch raises a visible warning. Export previews the Desktop layout and asks before overwriting; it copies (never moves) and keeps the timestamped workspace. Reset Workspace is explicit and confirmed.

---

## Settings

Settings (gear / `hamlet-ai` config at `~/.config/hamlet-ai/settings.json`) are written atomically and **never** include API keys. Editable: model IDs per provider, voice settings, retention TTLs, recording target seconds, the performance target, and per-provider **Test Connection** with last-tested timestamps.

---

## Doctor

```bash
hamlet-ai doctor
```

Checks: ElevenLabs key (and `list_voices` when live), Anthropic/OpenAI/Ollama connectivity, write access to `RUNS/`/`LINES/`/`LLM-H`, `clone.txt` parses, QLab `ghost_*.mp3` present, stale samples in legacy `SAMPLE/`, retention sweep due, DRY_RUN status, and audio input devices. Exit code: `0` all green, `1` warnings, `2` errors.

---

## Show Mode

Toggle Show Mode to lock risky controls during a performance: Settings, Reset Workspace, Delete Voice, Restore-without-confirm, and Edit Character Voices are disabled, and prominent fallback buttons (Restore last good LINES/, Use stock Ghost voice, Regenerate selected line, Open QLab folder) are surfaced. With Show Mode on, volunteer labels are masked in the log pane.

### Consent & Retention

No clone proceeds without an explicit consent record (volunteer label, confirmed-by-operator, retention policy), stored in the run's `clone_metadata.json` and on the voice-library entry. Retention policies: `keep` (default), `delete_after_show` (swept after a configurable TTL, default 24h), and `ephemeral` (deleted locally and from ElevenLabs at end of session). Ephemeral Show Mode forces every new clone to `ephemeral`.

---

## DRY_RUN Mode

With DRY_RUN on (the default), no API key is required and no ElevenLabs calls are made. `synthesize` writes a **real, short, silent, playable** audio file (so QLab and the in-app player both work), and the clone/poll steps short-circuit with a mock voice id. Set DRY_RUN **off** (`--dry-run` omitted, or the GUI toggle) for a real show.

Before rehearsal, do one real round-trip: turn DRY_RUN off and run a 5-second clone to confirm the key and quota.

---

## Pre-Show Startup Checklist

1. `source .venv/bin/activate` (or double-click `scripts/hamlet-ai.command`).
2. Confirm `.env` has a valid `ELEVENLABS_API_KEY`.
3. Run `hamlet-ai doctor` — resolve any ❌ errors, acknowledge ⚠️ warnings.
4. Confirm `clone.txt` has the right cues and the QLab `ghost_*.mp3` filenames match.
5. Do one real (non-DRY_RUN) 5-second clone to verify the API and quota.
6. Clear stale files from legacy `SAMPLE/`.
7. Turn DRY_RUN **off**.
8. Enable **Show Mode**.
9. Keep the **Archive → Restore last good** path in mind as the rescue.

---

## CLI Examples

```bash
# Voice clone (consent is mandatory):
hamlet-ai voice-clone --i-consent --volunteer "Row F seat 12" --retention delete_after_show

# Dry-run voice clone (no key needed):
hamlet-ai voice-clone --dry-run --i-consent

# Script generation (non-interactive):
hamlet-ai script-gen --play Hamlet --scene "Act I, Scene 1" \
  --character-count 3 --character-name HAMLET --include "a raven" \
  --style brooding --llm anthropic
```

---

## Testing

The full pyramid (unit + integration + GUI) runs headless:

```bash
QT_QPA_PLATFORM=offscreen pytest tests/ -v
```

CI runs lint + the offscreen test suite on Linux (`.github/workflows/ci.yml`). A macOS smoke run (audio + microphone permission) is manual.

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| `No audio file found in SAMPLE/` | Put one recording in `~/Desktop/VOICE-CLONE/SAMPLE/`. |
| `Script file not found` | Confirm `clone.txt` is in `VOICE-CLONE/SCRIPT/`. |
| `ELEVENLABS_API_KEY not set` (live run) | Check `.env` and that `python-dotenv` is installed. DRY_RUN does not need a key. |
| Clone fails 401 | Key invalid/expired — rotate it at the ElevenLabs dashboard. |
| Clone fails 422 | Audio rejected — confirm a valid, uncorrupted mp3/wav. |
| Voice times out | Polls for 120s; check status.elevenlabs.io. The poll loop now retries transient network errors. |
| Ollama provider failing | Start the daemon (`ollama serve`) and pull the model in Settings. |

---

## Project

**Production:** Hamlet.AI — Wember / Wolf359
**Platform:** Mac Mini M4 / macOS (Linux for CI)
**API:** ElevenLabs Instant Voice Cloning; Anthropic / OpenAI / Ollama for Script Gen
