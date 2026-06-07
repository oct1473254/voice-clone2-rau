# HAMLET.AI — Voice Clone System
### Wember / Wolf359

A Python script that captures a live audience volunteer's voice, clones it via the ElevenLabs Instant Voice Cloning API, and generates pre-scripted ghost lines in that voice — ready for immediate QLab playback.

---

## Overview

During a live scene, an audience volunteer speaks for approximately 90 seconds. The script captures that recording, sends it to ElevenLabs, creates a voice clone, and generates a set of pre-written lines in the volunteer's voice. The resulting audio files drop directly into a watched folder and are pre-mapped to QLab cues.

The full process — from audio capture to generated files — typically completes in under two minutes.

---

## System Requirements

- **macOS** (developed on Mac Mini M4)
- **Python 3.10+**
- **ElevenLabs account** with Instant Voice Cloning access (Starter plan or above)
- **QLab** (for playback — handled separately, not by this script)

---

## Folder Structure

All working folders live under `~/Desktop/VOICE-CLONE/`:

```
VOICE-CLONE/
├── SCRIPT/
│   └── clone.txt          # Pre-written ghost lines with filenames
├── SAMPLE/                # Drop volunteer audio recording here before running
├── LINES/                 # Generated mp3 files appear here — QLab points here
└── ARCHIVE/               # Previous runs archived automatically by timestamp
```

The script creates these folders on first run if they don't exist.

---

## Installation

**1. Clone or copy the project files:**
```
voiceclone2.py
clone.txt  →  place in VOICE-CLONE/SCRIPT/
```

**2. Create a virtual environment:**
```bash
python3 -m venv .venv
source .venv/bin/activate
```

**3. Install dependencies:**
```bash
pip install requests python-dotenv
```

**4. Create a `.env` file** in the project root:
```
ELEVENLABS_API_KEY=your_api_key_here
```
Never commit this file. It is excluded by `.gitignore`.

---

## Configuration

At the top of `voiceclone2.py`:

```python
DRY_RUN  = False          # Set True to test without API calls
MODEL_ID = "eleven_v3"    # Swap to eleven_multilingual_v2 if needed
```

**Voice settings** (also at top of script):
```python
VOICE_SETTINGS = {
    "stability":        0.2,
    "similarity_boost": 0.75,
    "speed":            1.2
}
```

Adjust `speed` between `0.7` (slower) and `1.2` (faster). Lower `stability` values produce more expressive, variable delivery.

---

## The Script File — clone.txt

Located at `VOICE-CLONE/SCRIPT/clone.txt`. Each entry is a filename line followed by the text block, separated by two blank lines:

```
ghost_00_sample.mp3
Hi, I'm Audience Burt. [pause] Nice to meet you.


ghost_01_shakespeare.mp3
List, [pause] list, [pause] O, list!
If thou didst ever thy dear father love — [long pause]
Revenge his foul and most unnatural murder.


ghost_02_modern.mp3
Very bad murder, [pause] as all murders are...
```

**Pause tags** follow ElevenLabs v3 syntax:
- `[pause]` — short pause
- `[long pause]` — longer pause

These are interpreted by the eleven_v3 model. They have no effect on eleven_multilingual_v2.

The German version (`ghost_03_german.mp3`) is a placeholder pending script revision.

---

## Pre-Show Operator Workflow

**1. Record the volunteer audio**
Capture approximately 90 seconds of the volunteer speaking naturally. MP3 at 192kbps or above is recommended. WAV is acceptable but offers no quality advantage over a good MP3.

**2. Name and place the file**
Drop the recording into:
```
~/Desktop/VOICE-CLONE/SAMPLE/
```
Only one file should be in SAMPLE/ when the script runs. If multiple files are present, the script will use the first one alphabetically and warn in the terminal.

**3. Run the script**
```bash
python voiceclone2.py
```

**4. Watch the terminal**
The script reports progress at each stage. A typical run looks like:
```
🎭 HAMLET.AI — VOICE CLONE SCRIPT
========================================
⚡ Starting concurrent tasks...
🎤 Starting voice clone...
🗂️  Running cleanup...
📄 Parsing script file...
   ✅ Loaded: ghost_00_sample.mp3
   ✅ Loaded: ghost_01_shakespeare.mp3
   ✅ Loaded: ghost_02_modern.mp3
🗂️  Cleanup complete.
📄 Script parsed: 3 lines ready.
   ✅ Clone created. Voice ID: abc123...
🔍 Confirming voice status...
   ✅ Voice ready after 0s.
🎙️  Generating 3 lines...
   [1/3] ghost_00_sample.mp3
   ✅ Saved: ghost_00_sample.mp3
   [2/3] ghost_01_shakespeare.mp3
   ✅ Saved: ghost_01_shakespeare.mp3
   [3/3] ghost_02_modern.mp3
   ✅ Saved: ghost_02_modern.mp3
✅ All lines generated.
🎭 Done. Files are in LINES/ and ready for QLab.
```

**5. Confirm files in LINES/**
QLab cues are pre-mapped to filenames in `VOICE-CLONE/LINES/`. Files appear there automatically. No QLab reconfiguration needed between runs.

---

## Archive System

At the start of each run, the script automatically:
- Reads the timestamp of the oldest file currently in `LINES/`
- Creates a subfolder in `ARCHIVE/` named by that timestamp (e.g. `20260601_193042/`)
- Moves all files from `LINES/` and `SAMPLE/` into that subfolder

This means every previous run is preserved with its source recording alongside the generated lines. If something goes wrong mid-show, previous versions are recoverable from `ARCHIVE/`.

---

## Dry Run Mode

To test the full script flow without making any API calls or consuming credits:

```python
DRY_RUN = True
```

In dry run mode:
- `clone_voice()` skips the API call and returns a mock voice ID after a 2-second delay
- `wait_for_voice()` skips polling
- `synthesize()` writes small text placeholder files to `LINES/` instead of mp3s

Useful for verifying folder structure, archive behavior, and script parsing before a show.

---

## ElevenLabs Model Notes

| Model | German | Pause Tags | Notes |
|---|---|---|---|
| `eleven_v3` | ✅ | `[pause]` `[long pause]` | Most expressive, recommended |
| `eleven_multilingual_v2` | ✅ | Not supported | More consistent, good fallback |
| `eleven_flash_v2_5` | ✅ | Not supported | Fast, lower quality |

For bilingual volunteers: if the volunteer is a native German speaker, record the sample in German. If they are a native English speaker who also speaks German, recording in English typically produces a cleaner clone.

---

## QLab Integration

QLab cues should be pre-mapped to:
```
~/Desktop/VOICE-CLONE/LINES/ghost_00_sample.mp3
~/Desktop/VOICE-CLONE/LINES/ghost_01_shakespeare.mp3
~/Desktop/VOICE-CLONE/LINES/ghost_02_modern.mp3
~/Desktop/VOICE-CLONE/LINES/ghost_03_german.mp3
```

Because filenames are fixed and the script always writes to the same paths, QLab cues require no reconfiguration between runs. Files are simply overwritten with the new volunteer's voice each time.

---

## Troubleshooting

**"No audio file found in SAMPLE/"**
Place the volunteer recording in `~/Desktop/VOICE-CLONE/SAMPLE/` before running.

**"Script file not found"**
Confirm `clone.txt` is in `~/Desktop/VOICE-CLONE/SCRIPT/`.

**"ELEVENLABS_API_KEY not set"**
Check that `.env` exists in the project root and contains the key. Confirm `python-dotenv` is installed.

**Clone fails with 401**
API key is invalid or expired. Check your ElevenLabs account.

**Clone fails with 422**
Audio file format issue. Confirm the file is a valid mp3 or wav and is not corrupted.

**Voice times out**
The script polls for 120 seconds before giving up. ElevenLabs IVC is typically ready in under 30 seconds. A timeout may indicate an API issue — check status.elevenlabs.io.

---

## Project

**Production:** Hamlet.AI — Wember / Wolf359
**Platform:** Mac Mini M4 / macOS
**Dependencies:** `requests`, `python-dotenv`
**API:** ElevenLabs Instant Voice Cloning
