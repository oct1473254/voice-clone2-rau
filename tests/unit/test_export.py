"""Step 6: export copies (does not move) workspace artifacts to Desktop."""
from __future__ import annotations

from pathlib import Path

import pytest

from hamlet_ai.core.script_gen.export import copy_to_desktop, reset_workspace


def _populate_workspace(workspace: Path) -> None:
    (workspace / "valid_lines" / "English").mkdir(parents=True)
    (workspace / "valid_lines" / "English" / "001-HAMLET.txt").write_text("HAMLET: Hi.")
    (workspace / "valid_lines" / "English" / "output").mkdir()
    (workspace / "valid_lines" / "English" / "output" / "001-HAMLET.mp3").write_bytes(b"AUDIO_EN")

    (workspace / "valid_lines" / "German").mkdir(parents=True)
    (workspace / "valid_lines" / "German" / "001-HAMLET.txt").write_text("HAMLET: Hallo.")

    (workspace / "cast_of_characters").mkdir()
    (workspace / "cast_of_characters" / "01-HAMLET.txt").touch()


def test_copy_to_desktop_populates_each_target(tmp_path):
    workspace = tmp_path / "ws"
    desktop = tmp_path / "Desktop" / "LLM-H"
    _populate_workspace(workspace)
    paths = copy_to_desktop(workspace, desktop, log_fn=lambda *_: None)
    assert (paths["audio"] / "001-HAMLET.mp3").read_bytes() == b"AUDIO_EN"
    assert (paths["text_english"] / "001-HAMLET.txt").read_text() == "HAMLET: Hi."
    assert (paths["text_german"] / "001-HAMLET.txt").read_text() == "HAMLET: Hallo."
    assert (paths["names"] / "01-HAMLET.txt").is_file()


def test_copy_to_desktop_is_not_destructive(tmp_path):
    """Workspace must remain intact after copy so the operator can re-run steps."""
    workspace = tmp_path / "ws"
    desktop = tmp_path / "Desktop" / "LLM-H"
    _populate_workspace(workspace)
    copy_to_desktop(workspace, desktop, log_fn=lambda *_: None)
    assert (workspace / "valid_lines" / "English" / "001-HAMLET.txt").is_file()
    assert (workspace / "valid_lines" / "English" / "output" / "001-HAMLET.mp3").is_file()


def test_copy_to_desktop_handles_missing_subfolders(tmp_path):
    """A run with only English (no German, no audio yet) shouldn't crash."""
    workspace = tmp_path / "ws"
    (workspace / "valid_lines" / "English").mkdir(parents=True)
    (workspace / "valid_lines" / "English" / "001-HAMLET.txt").write_text("HAMLET: Hi.")
    desktop = tmp_path / "Desktop" / "LLM-H"
    paths = copy_to_desktop(workspace, desktop, log_fn=lambda *_: None)
    assert (paths["text_english"] / "001-HAMLET.txt").is_file()
    assert paths["text_german"].is_dir()
    assert list(paths["text_german"].iterdir()) == []


def test_reset_workspace_clears_artifacts(tmp_path):
    workspace = tmp_path / "ws"
    _populate_workspace(workspace)
    reset_workspace(workspace, log_fn=lambda *_: None, confirm=True, backup=False)
    assert workspace.is_dir()
    assert list(workspace.iterdir()) == []


def test_reset_workspace_requires_confirm(tmp_path):
    workspace = tmp_path / "ws"
    _populate_workspace(workspace)
    with pytest.raises(ValueError):
        reset_workspace(workspace, log_fn=lambda *_: None)
    # Untouched.
    assert (workspace / "valid_lines" / "English" / "001-HAMLET.txt").is_file()


def test_reset_workspace_keeps_timestamped_backup(tmp_path):
    workspace = tmp_path / "ws"
    _populate_workspace(workspace)
    backup = reset_workspace(workspace, log_fn=lambda *_: None, confirm=True, now=0)
    assert backup is not None and backup.is_dir()
    assert (backup / "valid_lines" / "English" / "001-HAMLET.txt").is_file()
    assert list(workspace.iterdir()) == []


# ---------- preview + overwrite confirm -----------------------------------

def test_preview_destination_flags_overwrites(tmp_path):
    from hamlet_ai.core.script_gen.export import preview_destination

    workspace = tmp_path / "ws"
    desktop = tmp_path / "Desktop" / "LLM-H"
    _populate_workspace(workspace)
    # Pre-create one of the destination files so it shows as an overwrite.
    (desktop / "TextEnglish").mkdir(parents=True)
    (desktop / "TextEnglish" / "001-HAMLET.txt").write_text("old")

    preview = preview_destination(workspace, desktop)
    overwrite_names = [p.name for p in preview["overwrites"]]
    assert "001-HAMLET.txt" in overwrite_names
    assert len(preview["planned"]) >= 3


def test_copy_to_desktop_overwrite_declined_skips_existing(tmp_path):
    workspace = tmp_path / "ws"
    desktop = tmp_path / "Desktop" / "LLM-H"
    _populate_workspace(workspace)
    (desktop / "TextEnglish").mkdir(parents=True)
    (desktop / "TextEnglish" / "001-HAMLET.txt").write_text("KEEP ME")

    copy_to_desktop(
        workspace, desktop, log_fn=lambda *_: None, overwrite_confirm=lambda paths: False
    )
    # Declined → existing file preserved, new files still copied.
    assert (desktop / "TextEnglish" / "001-HAMLET.txt").read_text() == "KEEP ME"
    assert (desktop / "Audio" / "001-HAMLET.mp3").is_file()
