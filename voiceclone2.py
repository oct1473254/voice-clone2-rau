# --- VOICE CLONE 2 ---
# --- Wember / Wolf359 ---

import os
import time
import shutil
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed

from dotenv import load_dotenv
load_dotenv()

# --- CONFIGURATION ---
API_KEY = os.environ.get("ELEVENLABS_API_KEY")

if not API_KEY:
    raise EnvironmentError("❌ ELEVENLABS_API_KEY not set in environment variables.")

MODEL_ID        = "eleven_v3"                          # swap to eleven_multilingual_v2 if needed

BASE_DIR        = os.path.expanduser("~/Desktop/VOICE-CLONE")
SCRIPT_FILE     = os.path.join(BASE_DIR, "SCRIPT", "clone.txt")
SAMPLE_DIR      = os.path.join(BASE_DIR, "SAMPLE")
LINES_DIR       = os.path.join(BASE_DIR, "LINES")
ARCHIVE_DIR     = os.path.join(BASE_DIR, "ARCHIVE")

CLONE_POLL_INTERVAL = 5    # seconds between voice-ready checks
CLONE_TIMEOUT       = 120  # seconds before giving up on clone

VOICE_SETTINGS  = {
    "stability":        0.5,
    "similarity_boost": 0.75
}

# --- SETUP: ensure folders exist ---
for folder in [SAMPLE_DIR, LINES_DIR, ARCHIVE_DIR]:
    os.makedirs(folder, exist_ok=True)

if __name__ == "__main__":
    print("✅ VOICE-CLONE script loaded. Folders verified.")
    print(f"   SCRIPT : {SCRIPT_FILE}")
    print(f"   SAMPLE : {SAMPLE_DIR}")
    print(f"   LINES  : {LINES_DIR}")
    print(f"   ARCHIVE: {ARCHIVE_DIR}")