"""Redaction for anything that reaches the LogPane or ``run_log.txt``.

Two concerns:
  * **Secrets** — API keys must never appear in logs. Both explicitly-supplied
    secrets and well-known key shapes are masked with ``<REDACTED>``.
  * **Privacy in Show Mode** — when Show Mode is on, volunteer labels are masked
    with ``<volunteer>`` so a projected log pane can't leak a name.

Importing this module has no side effects.
"""
from __future__ import annotations

import re

REDACTED = "<REDACTED>"
VOLUNTEER = "<volunteer>"

# Well-known API key shapes (ElevenLabs sk_..., Anthropic sk-ant-..., OpenAI sk-...).
_KEY_PATTERNS = [
    re.compile(r"sk-ant-[A-Za-z0-9_-]{16,}"),
    re.compile(r"sk_[A-Za-z0-9]{16,}"),
    re.compile(r"sk-[A-Za-z0-9]{16,}"),
]


def redact(
    text,
    secrets: list[str] | None = None,
    volunteer_labels: list[str] | None = None,
    show_mode: bool = False,
) -> str:
    """Mask secrets (always) and volunteer labels (in Show Mode) in ``text``."""
    if text is None:
        return text
    s = str(text)
    for secret in secrets or []:
        if secret:
            s = s.replace(secret, REDACTED)
    for pat in _KEY_PATTERNS:
        s = pat.sub(REDACTED, s)
    if show_mode:
        for label in volunteer_labels or []:
            if label:
                s = s.replace(label, VOLUNTEER)
    return s
