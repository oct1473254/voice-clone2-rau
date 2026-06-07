"""Copy a script-gen workspace into the operator's Desktop layout.

The legacy ``Hamlet-gen5.move_folders_to_desktop`` MOVED files, wiping the
workspace and preventing re-runs. We COPY instead so the operator can re-export
or replay steps. ``reset_workspace`` is the explicit destructive operation.
"""
from __future__ import annotations

import shutil
from pathlib import Path
from typing import Callable


LogFn = Callable[[str], None]


def copy_to_desktop(
    workspace_dir: Path,
    desktop_root: Path,
    log_fn: LogFn = print,
) -> dict[str, Path]:
    """Copy workspace artifacts into ``desktop_root`` with the LLM-H layout.

    Layout written under ``desktop_root``::
        Audio/        (mp3s from workspace/valid_lines/English/output)
        TextEnglish/  (.txt from workspace/valid_lines/English)
        TextGerman/   (.txt from workspace/valid_lines/German)
        Names/        (.txt from workspace/cast_of_characters)
    """
    desktop_root.mkdir(parents=True, exist_ok=True)
    audio = desktop_root / "Audio"
    text_en = desktop_root / "TextEnglish"
    text_de = desktop_root / "TextGerman"
    names = desktop_root / "Names"
    for d in (audio, text_en, text_de, names):
        d.mkdir(exist_ok=True)

    en_output = workspace_dir / "valid_lines" / "English" / "output"
    if en_output.is_dir():
        for f in en_output.iterdir():
            if f.is_file():
                shutil.copy2(f, audio / f.name)
        log_fn(f"📦 Copied audio → {audio}")

    en_text = workspace_dir / "valid_lines" / "English"
    if en_text.is_dir():
        for f in en_text.iterdir():
            if f.is_file() and f.suffix == ".txt":
                shutil.copy2(f, text_en / f.name)
        log_fn(f"📦 Copied English text → {text_en}")

    de_text = workspace_dir / "valid_lines" / "German"
    if de_text.is_dir():
        for f in de_text.iterdir():
            if f.is_file() and f.suffix == ".txt":
                shutil.copy2(f, text_de / f.name)
        log_fn(f"📦 Copied German text → {text_de}")

    cast = workspace_dir / "cast_of_characters"
    if cast.is_dir():
        for f in cast.iterdir():
            if f.is_file() and f.suffix == ".txt":
                shutil.copy2(f, names / f.name)
        log_fn(f"📦 Copied cast → {names}")

    return {"audio": audio, "text_english": text_en, "text_german": text_de, "names": names}


def reset_workspace(workspace_dir: Path, log_fn: LogFn = print) -> None:
    """Clear all generated artifacts. Operator must confirm in the GUI."""
    if not workspace_dir.exists():
        return
    shutil.rmtree(workspace_dir)
    workspace_dir.mkdir(parents=True, exist_ok=True)
    log_fn(f"🧹 Workspace reset: {workspace_dir}")
