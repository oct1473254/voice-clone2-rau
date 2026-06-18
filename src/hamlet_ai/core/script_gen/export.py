"""Copy a script-gen workspace into the operator's Desktop layout.

The legacy ``Hamlet-gen5.move_folders_to_desktop`` MOVED files, wiping the
workspace and preventing re-runs. We COPY instead so the operator can re-export
or replay steps. ``reset_workspace`` is the only destructive operation and it
must be explicitly confirmed.

Step 6 additions:
  * ``preview_destination`` reports the planned copies and which existing files
    would be overwritten (drives the GUI's Export preview tree).
  * ``copy_to_desktop`` accepts an ``overwrite_confirm`` callback so the GUI can
    ask before clobbering existing Desktop files.
  * ``reset_workspace(confirm=True)`` keeps a timestamped backup by default.
"""
from __future__ import annotations

import shutil
import time
from pathlib import Path
from typing import Callable


LogFn = Callable[[str], None]
OverwriteConfirm = Callable[[list[Path]], bool]


# Each tuple: (workspace subpath, desktop target name, suffix filter or None).
# Audio is the performed (German) lines; TextGerman is what was voiced and
# TextEnglish is the review translation.
_PLAN_SPECS = [
    ("valid_lines/German/output", "Audio", None),
    ("valid_lines/German", "TextGerman", ".txt"),
    ("valid_lines/English", "TextEnglish", ".txt"),
    ("cast_of_characters", "Names", ".txt"),
]

_TARGET_KEYS = {
    "Audio": "audio",
    "TextEnglish": "text_english",
    "TextGerman": "text_german",
    "Names": "names",
}


def _build_plan(workspace_dir: Path, desktop_root: Path) -> list[tuple[Path, Path]]:
    """Return the list of (src_file, dest_file) copies that would be performed."""
    plan: list[tuple[Path, Path]] = []
    for sub, target_name, suffix in _PLAN_SPECS:
        src_dir = workspace_dir / sub
        if not src_dir.is_dir():
            continue
        dest_dir = desktop_root / target_name
        for f in sorted(src_dir.iterdir()):
            if not f.is_file():
                continue
            if suffix is not None and f.suffix != suffix:
                continue
            plan.append((f, dest_dir / f.name))
    return plan


def preview_destination(workspace_dir: Path, desktop_root: Path) -> dict:
    """Describe what ``copy_to_desktop`` would do without touching disk."""
    plan = _build_plan(workspace_dir, desktop_root)
    overwrites = [dest for _, dest in plan if dest.exists()]
    return {
        "planned": plan,
        "overwrites": overwrites,
        "new": [dest for _, dest in plan if not dest.exists()],
    }


def copy_to_desktop(
    workspace_dir: Path,
    desktop_root: Path,
    log_fn: LogFn = print,
    overwrite_confirm: OverwriteConfirm | None = None,
) -> dict[str, Path]:
    """Copy workspace artifacts into ``desktop_root`` with the LLM-H layout.

    If any existing Desktop files would be overwritten and ``overwrite_confirm``
    is provided, it is called with the list of those paths; returning False skips
    the overwriting copies (new files are still written).

    Layout written under ``desktop_root``::
        Audio/        (mp3s from workspace/valid_lines/English/output)
        TextEnglish/  (.txt from workspace/valid_lines/English)
        TextGerman/   (.txt from workspace/valid_lines/German)
        Names/        (.txt from workspace/cast_of_characters)
    """
    desktop_root.mkdir(parents=True, exist_ok=True)
    targets = {name: desktop_root / name for name in _TARGET_KEYS}
    for d in targets.values():
        d.mkdir(exist_ok=True)

    plan = _build_plan(workspace_dir, desktop_root)
    overwrites = [dest for _, dest in plan if dest.exists()]
    allow_overwrite = True
    if overwrites and overwrite_confirm is not None:
        allow_overwrite = bool(overwrite_confirm(overwrites))
        if not allow_overwrite:
            log_fn(f"⚠️  Skipping {len(overwrites)} existing file(s) (overwrite declined).")

    # Mirror, don't merge: remove files left in a managed target by a previous
    # run so the Desktop reflects ONLY this scene. Without this, a character or
    # line the last run had (a stray "FRED FLINTSTONE", a higher line count)
    # lingers in Names/Audio/Text* and breaks the show. A target is only synced
    # if this run produced something for it (its source subfolder exists), so a
    # partial run never silently wipes an unrelated target. Skipped entirely
    # when the operator declined the overwrite prompt.
    planned_dests = {dest for _, dest in plan}
    removed = 0
    if allow_overwrite:
        for sub, target_name, _suffix in _PLAN_SPECS:
            if not (workspace_dir / sub).is_dir():
                continue
            dest_dir = desktop_root / target_name
            if not dest_dir.is_dir():
                continue
            for existing in dest_dir.iterdir():
                if existing.is_file() and existing not in planned_dests:
                    existing.unlink()
                    removed += 1
    if removed:
        log_fn(f"🧹 Removed {removed} stale file(s) from previous run(s).")

    copied = 0
    for src, dest in plan:
        if dest.exists() and not allow_overwrite:
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
        copied += 1
    log_fn(f"📦 Copied {copied} file(s) → {desktop_root}")

    return {key: targets[name] for name, key in _TARGET_KEYS.items()}


def reset_workspace(
    workspace_dir: Path,
    log_fn: LogFn = print,
    *,
    confirm: bool = False,
    backup: bool = True,
    now: float | None = None,
) -> Path | None:
    """Clear all generated artifacts. Requires ``confirm=True``.

    By default the existing workspace is moved to a timestamped sibling
    (``{name}.reset-{ts}``) so artifacts are retained; pass ``backup=False`` to
    delete outright. Returns the backup path (or ``None``).
    """
    if not confirm:
        raise ValueError("reset_workspace is destructive; pass confirm=True to proceed.")
    if not workspace_dir.exists():
        workspace_dir.mkdir(parents=True, exist_ok=True)
        return None

    backup_path: Path | None = None
    has_content = any(workspace_dir.iterdir())
    if backup and has_content:
        ts = time.strftime("%Y%m%d_%H%M%S", time.localtime(now))
        backup_path = workspace_dir.parent / f"{workspace_dir.name}.reset-{ts}"
        suffix = 1
        while backup_path.exists():
            backup_path = workspace_dir.parent / f"{workspace_dir.name}.reset-{ts}_{suffix}"
            suffix += 1
        shutil.move(str(workspace_dir), str(backup_path))
        log_fn(f"🧹 Workspace reset; previous artifacts kept at {backup_path}")
    else:
        shutil.rmtree(workspace_dir)
        log_fn(f"🧹 Workspace reset: {workspace_dir}")

    workspace_dir.mkdir(parents=True, exist_ok=True)
    return backup_path


def clear_desktop_outputs(
    desktop_root: Path,
    log_fn: LogFn = print,
    *,
    confirm: bool = False,
) -> int:
    """Delete the generated text and audio under the Desktop layout.

    Empties the four export-owned folders (Audio, TextEnglish, TextGerman,
    Names) so no file from an earlier run survives. The folders themselves are
    kept (recreated empty). Requires ``confirm=True``. Returns the number of
    items removed.
    """
    if not confirm:
        raise ValueError("clear_desktop_outputs is destructive; pass confirm=True to proceed.")
    removed = 0
    for name in _TARGET_KEYS:
        target = desktop_root / name
        if not target.is_dir():
            continue
        for entry in target.iterdir():
            if entry.is_dir():
                shutil.rmtree(entry)
            else:
                entry.unlink()
            removed += 1
    log_fn(f"🧹 Cleared {removed} item(s) from {desktop_root}")
    return removed


def reset_all_outputs(
    workspace_dir: Path,
    desktop_root: Path,
    log_fn: LogFn = print,
    *,
    confirm: bool = False,
    backup: bool = True,
    now: float | None = None,
) -> Path | None:
    """Clear BOTH the workspace and the Desktop output folders.

    This is what the GUI's "Clear Old Runs" button calls so that no text or
    audio from a previous scene can survive into the next show. The workspace is
    kept as a timestamped backup by default (see :func:`reset_workspace`); the
    Desktop export folders are emptied outright. Requires ``confirm=True``.
    Returns the workspace backup path (or ``None``).
    """
    if not confirm:
        raise ValueError("reset_all_outputs is destructive; pass confirm=True to proceed.")
    backup_path = reset_workspace(
        workspace_dir, log_fn, confirm=True, backup=backup, now=now
    )
    clear_desktop_outputs(desktop_root, log_fn, confirm=True)
    return backup_path
