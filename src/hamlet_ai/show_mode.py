"""Show Mode lock policy (non-GUI).

Show Mode locks risky controls during a live performance and surfaces a small
set of one-tap fallback actions. Keeping the policy here (rather than in the GUI)
means it's testable headless and the CLI can consult it too.
"""
from __future__ import annotations

# Controls disabled while Show Mode is on.
LOCKED_ACTIONS = frozenset(
    {
        "settings",
        "reset_workspace",
        "delete_voice",
        "restore_from_archive_unconfirmed",
        "edit_character_voices",
    }
)

# Prominent rescue actions Show Mode adds.
FALLBACK_ACTIONS = (
    "restore_last_good",
    "use_stock_ghost_voice",
    "regenerate_selected_line",
    "open_qlab_folder",
)


def is_locked(action: str, show_mode: bool) -> bool:
    """True if ``action`` should be disabled given the current Show Mode state."""
    return bool(show_mode) and action in LOCKED_ACTIONS
