"""Split a generated scene into per-character per-line entries.

Pure data transformation — no filesystem I/O. ``write_split_files`` does the
disk writes in a separate function so ``split_script`` is trivial to test.
"""
from __future__ import annotations

import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path


# Allow upper-case names, spaces, and apostrophes (e.g. KING'S MESSENGER).
NAME_RE = re.compile(r"^[A-Z][A-Z ']*$")
PAREN_RE = re.compile(r"\(.*?\)")


@dataclass(frozen=True)
class ScriptLine:
    line_number: int  # 1-based, position in source script
    character: str
    dialogue: str


@dataclass
class ParsedScript:
    lines: list[ScriptLine]
    characters: list[str]  # sorted unique
    rejected: list[str]  # original raw lines that didn't parse


def split_script(text: str) -> ParsedScript:
    lines_out: list[ScriptLine] = []
    rejected: list[str] = []
    characters: set[str] = set()

    raw_lines = text.splitlines()
    for idx, raw in enumerate(raw_lines, start=1):
        if not raw.strip():
            continue
        if ":" not in raw:
            rejected.append(raw)
            continue
        name_part, dialogue_part = raw.split(":", 1)
        name = name_part.strip()
        if not NAME_RE.match(name):
            rejected.append(raw)
            continue
        cleaned = PAREN_RE.sub("", dialogue_part).strip()
        if not cleaned:
            # No dialogue worth synthesizing; treat as rejected for visibility.
            rejected.append(raw)
            continue
        characters.add(name)
        lines_out.append(ScriptLine(line_number=idx, character=name, dialogue=cleaned))

    return ParsedScript(
        lines=lines_out,
        characters=sorted(characters),
        rejected=rejected,
    )


def _atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(content)
        os.replace(tmp_name, path)
    except Exception:
        try:
            os.unlink(tmp_name)
        except FileNotFoundError:
            pass
        raise


def write_split_files(parsed: ParsedScript, workspace_dir: Path, language: str) -> dict[str, Path]:
    """Write valid lines, rejected lines, and cast files into the workspace.

    Layout:
        workspace_dir/valid_lines/{language}/{NNN}-{CHARACTER}.txt
        workspace_dir/rejected_lines/rejected_lines_{language}.txt
        workspace_dir/cast_of_characters/{NN}-{CHARACTER}.txt  (empty marker files)

    Returns a dict mapping logical keys to the directories/files created.
    """
    valid_dir = workspace_dir / "valid_lines" / language
    rejected_dir = workspace_dir / "rejected_lines"
    cast_dir = workspace_dir / "cast_of_characters"
    valid_dir.mkdir(parents=True, exist_ok=True)
    rejected_dir.mkdir(parents=True, exist_ok=True)
    cast_dir.mkdir(parents=True, exist_ok=True)

    written_lines: list[Path] = []
    for line in parsed.lines:
        out = valid_dir / f"{line.line_number:03d}-{line.character}.txt"
        _atomic_write_text(out, f"{line.character}: {line.dialogue}")
        written_lines.append(out)

    rejected_path: Path | None = None
    if parsed.rejected:
        rejected_path = rejected_dir / f"rejected_lines_{language}.txt"
        _atomic_write_text(rejected_path, "\n".join(parsed.rejected) + "\n")

    cast_paths: list[Path] = []
    for idx, name in enumerate(parsed.characters, start=1):
        marker = cast_dir / f"{idx:02d}-{name}.txt"
        marker.touch()
        cast_paths.append(marker)

    return {
        "valid_dir": valid_dir,
        "rejected_path": rejected_path,
        "cast_dir": cast_dir,
        "lines_written": written_lines,
        "cast_written": cast_paths,
    }
