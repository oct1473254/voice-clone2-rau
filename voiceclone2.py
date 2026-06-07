# --- VOICE CLONE 2 ---
# --- Wember / Wolf359 ---

import os
import time
import shutil
import threading
import queue

import requests
from concurrent.futures import ThreadPoolExecutor, as_completed

from dotenv import load_dotenv
load_dotenv()

# --- CONFIGURATION ---
API_KEY = os.environ.get("ELEVENLABS_API_KEY")

if not API_KEY:
    raise EnvironmentError("❌ ELEVENLABS_API_KEY not set in environment variables.")

DRY_RUN  = True
MODEL_ID = "eleven_v3"                          # swap to eleven_multilingual_v2 if needed

BASE_DIR     = os.path.expanduser("~/Desktop/VOICE-CLONE")
SCRIPT_FILE  = os.path.join(BASE_DIR, "SCRIPT", "clone.txt")
SAMPLE_DIR   = os.path.join(BASE_DIR, "SAMPLE")
LINES_DIR    = os.path.join(BASE_DIR, "LINES")
ARCHIVE_DIR  = os.path.join(BASE_DIR, "ARCHIVE")

CLONE_POLL_INTERVAL = 5    # seconds between voice-ready checks
CLONE_TIMEOUT       = 120  # seconds before giving up on clone

VOICE_SETTINGS = {
    "stability":        0.3,
    "similarity_boost": 0.75,
    "speed":            1.2
}

# --- SETUP: ensure folders exist ---
for folder in [SAMPLE_DIR, LINES_DIR, ARCHIVE_DIR]:
    os.makedirs(folder, exist_ok=True)


# ---------------------------------------------------------------------------
# FUNCTIONS
# ---------------------------------------------------------------------------

def parse_script(script_file, log_fn=print):
    """Read clone.txt and return list of (filename, text) tuples."""
    log_fn("📄 Parsing script file...")
    lines = []

    if not os.path.exists(script_file):
        raise FileNotFoundError(f"❌ Script file not found: {script_file}")

    with open(script_file, "r", encoding="utf-8") as f:
        content = f.read()

    blocks = [b.strip() for b in content.split("\n\n") if b.strip()]

    for block in blocks:
        parts = block.split("\n", 1)
        if len(parts) == 2:
            filename = parts[0].strip()
            text = parts[1].strip()
            lines.append((filename, text))
            log_fn(f"   ✅ Loaded: {filename}")
        else:
            log_fn(f"   ⚠️ Skipping malformed block: {parts[0][:40]}")

    log_fn(f"📄 Script parsed: {len(lines)} lines ready.")
    return lines


def cleanup(log_fn=print):
    """Archive existing LINES and SAMPLE files before a new run."""
    log_fn("🗂️  Running cleanup...")

    lines_files = [f for f in os.listdir(LINES_DIR) if not f.startswith(".")]

    if not lines_files:
        log_fn("🗂️  LINES/ is empty, nothing to archive.")
        return

    oldest = min(
        lines_files,
        key=lambda f: os.path.getmtime(os.path.join(LINES_DIR, f))
    )
    timestamp = time.strftime(
        "%Y%m%d_%H%M%S",
        time.localtime(os.path.getmtime(os.path.join(LINES_DIR, oldest)))
    )

    archive_subfolder = os.path.join(ARCHIVE_DIR, timestamp)
    os.makedirs(archive_subfolder, exist_ok=True)
    log_fn(f"🗂️  Archiving to: ARCHIVE/{timestamp}/")

    for f in lines_files:
        try:
            shutil.move(os.path.join(LINES_DIR, f), os.path.join(archive_subfolder, f))
            log_fn(f"   → Moved from LINES/: {f}")
        except Exception as e:
            log_fn(f"   ⚠️ Could not move {f} from LINES/: {e}")

    sample_files = [f for f in os.listdir(SAMPLE_DIR) if not f.startswith(".")]
    if not sample_files:
        log_fn("🗂️  SAMPLE/ is empty, skipping.")
    else:
        for f in sample_files:
            try:
                shutil.move(os.path.join(SAMPLE_DIR, f), os.path.join(archive_subfolder, f))
                log_fn(f"   → Moved from SAMPLE/: {f}")
            except Exception as e:
                log_fn(f"   ⚠️ Could not move {f} from SAMPLE/: {e}")

    log_fn("🗂️  Cleanup complete.")


def clone_voice(sample_dir, log_fn=print):
    """Upload volunteer audio from SAMPLE/ to ElevenLabs IVC and return a voice_id."""
    log_fn("🎤 Starting voice clone...")

    audio_files = [f for f in os.listdir(sample_dir) if not f.startswith(".")]
    if not audio_files:
        raise FileNotFoundError("❌ No audio file found in SAMPLE/")
    if len(audio_files) > 1:
        log_fn(f"   ⚠️ Multiple files in SAMPLE/, using first: {audio_files[0]}")

    audio_path = os.path.join(sample_dir, audio_files[0])
    log_fn(f"   📁 Using: {audio_files[0]}")

    if DRY_RUN:
        log_fn("   🧪 DRY RUN — skipping API call, returning mock voice_id.")
        time.sleep(2)
        return "dry_run_voice_id_12345"

    url = "https://api.elevenlabs.io/v1/voices/add"
    headers = {"xi-api-key": API_KEY}

    with open(audio_path, "rb") as f:
        files = {"files": (audio_files[0], f, "audio/mpeg")}
        data  = {
            "name": "AudienceClone",
            "description": "Live audience voice clone"
        }
        response = requests.post(url, headers=headers, files=files, data=data)

    if response.status_code == 200:
        voice_id = response.json().get("voice_id")
        log_fn(f"   ✅ Clone created. Voice ID: {voice_id}")
        return voice_id
    else:
        raise RuntimeError(f"❌ Clone failed {response.status_code}: {response.text}")


def wait_for_voice(voice_id, log_fn=print):
    """Poll until the cloned voice is confirmed ready."""
    log_fn("⏳ Waiting for voice to be ready...")

    if DRY_RUN:
        log_fn("   🧪 DRY RUN — skipping poll, voice assumed ready.")
        return voice_id

    url = f"https://api.elevenlabs.io/v1/voices/{voice_id}"
    headers = {"xi-api-key": API_KEY}

    elapsed = 0
    while elapsed < CLONE_TIMEOUT:
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            log_fn(f"   ✅ Voice ready after {elapsed}s.")
            return voice_id
        elif response.status_code == 404:
            log_fn(f"   ⏳ Not ready yet... ({elapsed}s elapsed)")
            time.sleep(CLONE_POLL_INTERVAL)
            elapsed += CLONE_POLL_INTERVAL
        else:
            raise RuntimeError(f"❌ Voice status check failed {response.status_code}: {response.text}")

    raise TimeoutError(f"❌ Voice not ready after {CLONE_TIMEOUT}s. Aborting.")


def synthesize(voice_id, text, filename, log_fn=print):
    """Generate a single audio line and save to LINES/."""
    if DRY_RUN:
        out_path = os.path.join(LINES_DIR, filename)
        with open(out_path, "w") as f:
            f.write(f"DRY RUN — would synthesize with voice {voice_id}:\n{text}")
        log_fn(f"   🧪 DRY RUN — wrote placeholder: {filename}")
        return

    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
    headers = {
        "xi-api-key": API_KEY,
        "Content-Type": "application/json"
    }
    data = {
        "text": text,
        "model_id": MODEL_ID,
        "voice_settings": VOICE_SETTINGS
    }

    response = requests.post(url, headers=headers, json=data)
    if response.status_code == 200:
        out_path = os.path.join(LINES_DIR, filename)
        with open(out_path, "wb") as f:
            f.write(response.content)
        log_fn(f"   ✅ Saved: {filename}")
    else:
        log_fn(f"   ❌ Error on {filename} — {response.status_code}: {response.text}")


def generate_lines(voice_id, script_lines, log_fn=print):
    """Iterate parsed script lines and synthesize each one."""
    log_fn(f"🎙️  Generating {len(script_lines)} lines...")
    for idx, (filename, text) in enumerate(script_lines, 1):
        log_fn(f"   [{idx}/{len(script_lines)}] {filename}")
        synthesize(voice_id, text, filename, log_fn=log_fn)
    log_fn("✅ All lines generated.")


def main():
    print("\n🎭 HAMLET.AI — VOICE CLONE SCRIPT")
    print("=" * 40)

    # --- PHASE 1: Launch concurrent tasks ---
    print("\n⚡ Starting concurrent tasks...")
    with ThreadPoolExecutor(max_workers=3) as executor:
        future_voice   = executor.submit(clone_voice,  SAMPLE_DIR)
        future_cleanup = executor.submit(cleanup)
        future_script  = executor.submit(parse_script, SCRIPT_FILE)

        voice_id     = None
        script_lines = None

        for future in as_completed([future_voice, future_cleanup, future_script]):
            try:
                result = future.result()
                if future == future_voice:
                    voice_id = result
                elif future == future_script:
                    script_lines = result
            except Exception as e:
                print(f"\n❌ Fatal error: {e}")
                raise

    # --- PHASE 2: Confirm voice is ready ---
    print("\n🔍 Confirming voice status...")
    voice_id = wait_for_voice(voice_id)

    # --- PHASE 3: Generate lines ---
    generate_lines(voice_id, script_lines)

    print("\n🎭 Done. Files are in LINES/ and ready for QLab.")
    print("=" * 40)


# ---------------------------------------------------------------------------
# ENTRY POINT
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    main()
