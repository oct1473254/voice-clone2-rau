"""Step 6: export copies (does not move) workspace artifacts to Desktop."""
from __future__ import annotations

from pathlib import Path

import pytest

from hamlet_ai.core.script_gen.export import (
    clear_desktop_outputs,
    copy_to_desktop,
    reset_all_outputs,
    reset_workspace,
)


def _populate_workspace(workspace: Path) -> None:
    # German is the performed/voiced language; its output dir holds the audio.
    (workspace / "valid_lines" / "German").mkdir(parents=True)
    (workspace / "valid_lines" / "German" / "001-HAMLET.txt").write_text("HAMLET: Hallo.")
    (workspace / "valid_lines" / "German" / "output").mkdir()
    (workspace / "valid_lines" / "German" / "output" / "001-HAMLET.mp3").write_bytes(b"AUDIO_DE")

    # English is the review translation (text only).
    (workspace / "valid_lines" / "English").mkdir(parents=True)
    (workspace / "valid_lines" / "English" / "001-HAMLET.txt").write_text("HAMLET: Hi.")

    (workspace / "cast_of_characters").mkdir()
    (workspace / "cast_of_characters" / "01-HAMLET.txt").touch()


def test_copy_to_desktop_populates_each_target(tmp_path):
    workspace = tmp_path / "ws"
    desktop = tmp_path / "Desktop" / "LLM-H"
    _populate_workspace(workspace)
    paths = copy_to_desktop(workspace, desktop, log_fn=lambda *_: None)
    assert (paths["audio"] / "001-HAMLET.mp3").read_bytes() == b"AUDIO_DE"
    assert (paths["text_german"] / "001-HAMLET.txt").read_text() == "HAMLET: Hallo."
    assert (paths["text_english"] / "001-HAMLET.txt").read_text() == "HAMLET: Hi."
    assert (paths["names"] / "01-HAMLET.txt").is_file()


def test_copy_to_desktop_is_not_destructive(tmp_path):
    """Workspace must remain intact after copy so the operator can re-run steps."""
    workspace = tmp_path / "ws"
    desktop = tmp_path / "Desktop" / "LLM-H"
    _populate_workspace(workspace)
    copy_to_desktop(workspace, desktop, log_fn=lambda *_: None)
    assert (workspace / "valid_lines" / "German" / "001-HAMLET.txt").is_file()
    assert (workspace / "valid_lines" / "German" / "output" / "001-HAMLET.mp3").is_file()


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


# ---------- clear desktop / reset all -------------------------------------

def _populate_desktop(desktop: Path) -> None:
    for name, fname in (
        ("Audio", "001-HAMLET.mp3"),
        ("TextEnglish", "001-HAMLET.txt"),
        ("TextGerman", "001-HAMLET.txt"),
        ("Names", "01-HAMLET.txt"),
    ):
        (desktop / name).mkdir(parents=True)
        (desktop / name / fname).write_text("x")


def test_clear_desktop_outputs_empties_all_targets(tmp_path):
    desktop = tmp_path / "Desktop" / "LLM-H"
    _populate_desktop(desktop)
    removed = clear_desktop_outputs(desktop, log_fn=lambda *_: None, confirm=True)
    assert removed == 4
    for name in ("Audio", "TextEnglish", "TextGerman", "Names"):
        assert (desktop / name).is_dir()  # folder kept...
        assert list((desktop / name).iterdir()) == []  # ...but emptied


def test_clear_desktop_outputs_requires_confirm(tmp_path):
    desktop = tmp_path / "Desktop" / "LLM-H"
    _populate_desktop(desktop)
    with pytest.raises(ValueError):
        clear_desktop_outputs(desktop, log_fn=lambda *_: None)
    assert (desktop / "Names" / "01-HAMLET.txt").exists()  # untouched


def test_reset_all_outputs_clears_workspace_and_desktop(tmp_path):
    workspace = tmp_path / "ws"
    desktop = tmp_path / "Desktop" / "LLM-H"
    _populate_workspace(workspace)
    _populate_desktop(desktop)
    reset_all_outputs(
        workspace, desktop, log_fn=lambda *_: None, confirm=True, backup=False
    )
    assert list(workspace.iterdir()) == []
    for name in ("Audio", "TextEnglish", "TextGerman", "Names"):
        assert list((desktop / name).iterdir()) == []


def test_reset_all_outputs_requires_confirm(tmp_path):
    with pytest.raises(ValueError):
        reset_all_outputs(tmp_path / "ws", tmp_path / "d", log_fn=lambda *_: None)


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


def test_copy_to_desktop_removes_stale_files_from_previous_run(tmp_path):
    """A character/line a previous run produced must not linger on the Desktop.

    Regression: the cast and per-line dirs accumulated across runs, so stale
    names (e.g. a fourth speaker only the last cast had) kept showing up in the
    Desktop folder and broke the show.
    """
    workspace = tmp_path / "ws"
    desktop = tmp_path / "Desktop" / "LLM-H"
    _populate_workspace(workspace)

    # Simulate leftovers from an earlier export: an extra name and an extra line.
    (desktop / "Names").mkdir(parents=True)
    (desktop / "Names" / "02-FRED FLINTSTONE.txt").touch()
    (desktop / "TextGerman").mkdir(parents=True)
    (desktop / "TextGerman" / "099-GERTRUDE.txt").write_text("GERTRUDE: alt")
    (desktop / "Audio").mkdir(parents=True)
    (desktop / "Audio" / "099-GERTRUDE.mp3").write_bytes(b"OLD")

    copy_to_desktop(workspace, desktop, log_fn=lambda *_: None)

    assert not (desktop / "Names" / "02-FRED FLINTSTONE.txt").exists()
    assert not (desktop / "TextGerman" / "099-GERTRUDE.txt").exists()
    assert not (desktop / "Audio" / "099-GERTRUDE.mp3").exists()
    # Current run's files are present.
    assert (desktop / "Names" / "01-HAMLET.txt").is_file()
    assert (desktop / "TextGerman" / "001-HAMLET.txt").is_file()


def test_copy_to_desktop_leaves_unmanaged_target_alone(tmp_path):
    """A run with no German must not wipe a prior German export off the Desktop."""
    workspace = tmp_path / "ws"
    (workspace / "valid_lines" / "English").mkdir(parents=True)
    (workspace / "valid_lines" / "English" / "001-HAMLET.txt").write_text("HAMLET: Hi.")
    desktop = tmp_path / "Desktop" / "LLM-H"
    (desktop / "TextGerman").mkdir(parents=True)
    (desktop / "TextGerman" / "001-HAMLET.txt").write_text("HAMLET: Hallo.")

    copy_to_desktop(workspace, desktop, log_fn=lambda *_: None)

    # German source folder was absent this run → its Desktop target untouched.
    assert (desktop / "TextGerman" / "001-HAMLET.txt").read_text() == "HAMLET: Hallo."


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
