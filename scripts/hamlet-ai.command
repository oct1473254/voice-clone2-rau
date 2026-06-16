#!/bin/bash
# Double-clickable macOS launcher for the Hamlet.AI GUI.
#
# Drag this file to the Dock or double-click it in Finder. It delegates to the
# cross-platform launcher (hamlet-ai.sh), which creates/activates the project
# virtualenv on first run, loads .env, and launches `hamlet-ai gui`. Keep it
# inside the repo's scripts/ folder so it can find the project root.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec "$SCRIPT_DIR/hamlet-ai.sh"
