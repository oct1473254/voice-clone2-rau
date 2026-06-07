"""Step 6: scene → ParsedScript transformation and on-disk write."""
from __future__ import annotations

from pathlib import Path

import pytest

from hamlet_ai.core.script_gen.line_splitter import (
    ParsedScript,
    ScriptLine,
    split_script,
    write_split_files,
)


SAMPLE_SCRIPT = """HAMLET: To be or not to be.
GERTRUDE: Speak no more, sweet son.
POLONIUS: (sadly) Though this be madness, yet there is method.
HAMLET: Words, words, words.

random line that doesn't match
KING'S MESSENGER: The king has fallen.
HAMLET:
"""


def test_split_script_returns_parsed_lines():
    parsed = split_script(SAMPLE_SCRIPT)
    assert isinstance(parsed, ParsedScript)
    chars = [line.character for line in parsed.lines]
    assert "HAMLET" in chars
    assert "POLONIUS" in chars
    assert "KING'S MESSENGER" in chars


def test_split_script_strips_parenthetical_directions():
    parsed = split_script("POLONIUS: (sadly) Though this be madness.")
    assert parsed.lines[0].dialogue == "Though this be madness."


def test_split_script_collects_characters_sorted_unique():
    parsed = split_script(SAMPLE_SCRIPT)
    assert parsed.characters == sorted(set(parsed.characters))
    assert "HAMLET" in parsed.characters


def test_split_script_rejects_non_matching_lines():
    parsed = split_script(SAMPLE_SCRIPT)
    assert any("random line" in r for r in parsed.rejected)


def test_split_script_rejects_lines_with_empty_dialogue():
    parsed = split_script("HAMLET: ")
    assert parsed.lines == []
    assert parsed.rejected == ["HAMLET: "]


def test_split_script_line_numbers_correspond_to_source_position():
    parsed = split_script(SAMPLE_SCRIPT)
    nums = [line.line_number for line in parsed.lines]
    assert nums == sorted(nums)
    assert nums[0] == 1


def test_write_split_files_creates_expected_layout(tmp_path):
    parsed = ParsedScript(
        lines=[
            ScriptLine(1, "HAMLET", "Words, words."),
            ScriptLine(2, "GERTRUDE", "Speak no more."),
        ],
        characters=["GERTRUDE", "HAMLET"],
        rejected=["bad line"],
    )
    paths = write_split_files(parsed, tmp_path, language="English")
    valid_dir = tmp_path / "valid_lines" / "English"
    assert (valid_dir / "001-HAMLET.txt").read_text() == "HAMLET: Words, words."
    assert (valid_dir / "002-GERTRUDE.txt").read_text() == "GERTRUDE: Speak no more."
    rejected = tmp_path / "rejected_lines" / "rejected_lines_English.txt"
    assert rejected.read_text().strip() == "bad line"
    cast_dir = tmp_path / "cast_of_characters"
    assert (cast_dir / "01-GERTRUDE.txt").is_file()
    assert (cast_dir / "02-HAMLET.txt").is_file()
    assert paths["valid_dir"] == valid_dir


def test_write_split_files_skips_rejected_file_when_no_rejects(tmp_path):
    parsed = ParsedScript(
        lines=[ScriptLine(1, "HAMLET", "Hi.")],
        characters=["HAMLET"],
        rejected=[],
    )
    write_split_files(parsed, tmp_path, language="English")
    assert not (tmp_path / "rejected_lines" / "rejected_lines_English.txt").exists()
