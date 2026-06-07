"""Unit tests for the Show Mode lock policy."""
from __future__ import annotations

from hamlet_ai.show_mode import FALLBACK_ACTIONS, LOCKED_ACTIONS, is_locked


def test_locked_actions_disabled_only_in_show_mode():
    assert is_locked("settings", show_mode=True) is True
    assert is_locked("settings", show_mode=False) is False


def test_unknown_action_never_locked():
    assert is_locked("play_line", show_mode=True) is False


def test_all_documented_controls_are_locked():
    for action in ("settings", "reset_workspace", "delete_voice", "edit_character_voices"):
        assert action in LOCKED_ACTIONS
        assert is_locked(action, True) is True


def test_fallbacks_present():
    assert "restore_last_good" in FALLBACK_ACTIONS
    assert "open_qlab_folder" in FALLBACK_ACTIONS
