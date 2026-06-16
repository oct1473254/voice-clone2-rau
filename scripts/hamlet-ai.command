#!/bin/bash
# Double-clickable macOS launcher for the Hamlet.AI GUI.
#
# Drag this file to the Dock or double-click it in Finder. It activates the
# project virtual environment (creating it on first run) and launches
# `hamlet-ai gui`. Keep it inside the repo's scripts/ folder so it can find
# the project root.
set -euo pipefail

# Resolve the repo root (this script lives in <repo>/scripts/).
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_DIR"

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

exec hamlet-ai gui
