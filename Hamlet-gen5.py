"""Backward-compatibility shim. The real script-generation pipeline now lives
under ``hamlet_ai.core.script_gen``. Operators who still run
``python Hamlet-gen5.py`` get the original interactive flow.

The original module hardcoded an ElevenLabs API key on line 204 — that key has
been scrubbed; both tools now read ``ELEVENLABS_API_KEY`` from the environment.
The operator should rotate the leaked key separately at ElevenLabs.
"""
from __future__ import annotations

from dotenv import load_dotenv

from hamlet_ai.cli import main


def _main() -> None:
    load_dotenv()
    raise SystemExit(main(["script-gen", "--interactive"]))


if __name__ == "__main__":
    _main()
