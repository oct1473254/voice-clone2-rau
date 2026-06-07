"""Split a generated scene into per-character per-line entries.

Pure data transformation — no filesystem I/O. ``write_split_files`` does the
disk writes in a separate function so ``split_script`` is trivial to test.

Tolerances (Step 6):
  * Character names may contain spaces, apostrophes, hyphens, accents, and
    digits: ``KING'S MESSENGER``, ``JEAN-PAUL``, ``ÉLODIE``, ``SERVANT 2``.
  * Colons inside dialogue are preserved (``HAMLET: To eat: or not.``).
  * Every spoken line gets a stable ``line_id``.
  * Standalone stage directions (a whole line wrapped in ``()`` / ``[]``) are
    captured as ``text_only`` directions rather than discarded.
  * Rejected lines carry a machine-readable ``reason`` code.
"""
from __future__ import annotations

import os
import re
import tempfile
from dataclasses import dataclass, field
from pathlib import Path


PAREN_RE = re.compile(r"\(.*?\)")
# A whole line that is purely a parenthesised/bracketed stage direction.
STAGE_DIRECTION_RE = re.compile(r"^\s*[\(\[].*[\)\]]\s*$")
# Allowed name punctuation (besides letters/digits).
_NAME_PUNCT = set(" '-.")


def _is_character_name(name: str) -> bool:
    """True if ``name`` reads as an ALL-CAPS speaker label.

    Accepts accented uppercase letters, spaces, apostrophes, hyphens, periods,
    and digits. Rejects anything containing a lowercase letter.
    """
    if not name:
        return False
    has_letter = False
    for ch in name:
        if ch.isalpha():
            has_letter = True
            if not ch.isupper():
                return False
        elif ch.isdigit() or ch in _NAME_PUNCT:
            continue
        else:
            return False
    return has_letter


@dataclass(frozen=True)
class ScriptLine:
    line_number: int  # 1-based, position in source script
    character: str
    dialogue: str
    line_id: str = ""  # stable id (derived from line_number by split_script)
    spoken: bool = True
    text_only: bool = False


@dataclass(frozen=True)
class RejectedLine:
    line_number: int
    raw: str
    reason: str  # machine-readable code


@dataclass
class ParsedScript:
    lines: list[ScriptLine]
    characters: list[str]  # sorted unique
    rejected: list[str]  # original raw lines that didn't parse (back-compat)
    rejected_details: list[RejectedLine] = field(default_factory=list)
    directions: list[ScriptLine] = field(default_factory=list)


def _line_id(line_number: int) -> str:
    return f"L{line_number:04d}"


def split_script(text: str) -> ParsedScript:
    lines_out: list[ScriptLine] = []
    rejected: list[str] = []
    rejected_details: list[RejectedLine] = []
    directions: list[ScriptLine] = []
    characters: set[str] = set()

    raw_lines = text.splitlines()
    for idx, raw in enumerate(raw_lines, start=1):
        if not raw.strip():
            continue

        # Whole-line stage direction → keep as a text-only entry.
        if STAGE_DIRECTION_RE.match(raw):
            directions.append(
                ScriptLine(
                    line_number=idx,
                    character="",
                    dialogue=raw.strip(),
                    line_id=_line_id(idx),
                    spoken=False,
                    text_only=True,
                )
            )
            continue

        if ":" not in raw:
            rejected.append(raw)
            rejected_details.append(RejectedLine(idx, raw, "no_colon"))
            continue

        # Split on the FIRST colon only, so colons inside dialogue survive.
        name_part, dialogue_part = raw.split(":", 1)
        name = name_part.strip()
        if not _is_character_name(name):
            rejected.append(raw)
            rejected_details.append(RejectedLine(idx, raw, "bad_character_name"))
            continue

        cleaned = PAREN_RE.sub("", dialogue_part).strip()
        if not cleaned:
            rejected.append(raw)
            rejected_details.append(RejectedLine(idx, raw, "empty_dialogue"))
            continue

        characters.add(name)
        lines_out.append(
            ScriptLine(
                line_number=idx,
                character=name,
                dialogue=cleaned,
                line_id=_line_id(idx),
                spoken=True,
                text_only=False,
            )
        )

    return ParsedScript(
        lines=lines_out,
        characters=sorted(characters),
        rejected=rejected,
        rejected_details=rejected_details,
        directions=directions,
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
