"""Step 6: scene → ParsedScript transformation and on-disk write."""
from __future__ import annotations



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


def test_write_split_files_replaces_previous_run(tmp_path):
    """A re-run must not leave the prior run's cast/line files in the workspace.

    Regression: stale per-character/per-line files survived across runs and were
    copied to the Desktop, so names from old scenes kept appearing.
    """
    first = ParsedScript(
        lines=[ScriptLine(1, "HAMLET", "A."), ScriptLine(2, "GERTRUDE", "B.")],
        characters=["GERTRUDE", "HAMLET"],
        rejected=["junk"],
    )
    write_split_files(first, tmp_path, language="German")

    second = ParsedScript(
        lines=[ScriptLine(1, "HAMLET", "C.")],
        characters=["HAMLET"],
        rejected=[],
    )
    write_split_files(second, tmp_path, language="German")

    valid_dir = tmp_path / "valid_lines" / "German"
    assert sorted(p.name for p in valid_dir.glob("*.txt")) == ["001-HAMLET.txt"]
    cast_dir = tmp_path / "cast_of_characters"
    assert sorted(p.name for p in cast_dir.glob("*.txt")) == ["01-HAMLET.txt"]
    # The first run's rejected file is gone since the second run rejected nothing.
    assert not (tmp_path / "rejected_lines" / "rejected_lines_German.txt").exists()


def test_write_split_files_skips_rejected_file_when_no_rejects(tmp_path):
    parsed = ParsedScript(
        lines=[ScriptLine(1, "HAMLET", "Hi.")],
        characters=["HAMLET"],
        rejected=[],
    )
    write_split_files(parsed, tmp_path, language="English")
    assert not (tmp_path / "rejected_lines" / "rejected_lines_English.txt").exists()


# ---------- Step 6: tolerant splitter -------------------------------------

def test_splitter_handles_colons_in_dialogue():
    parsed = split_script("HAMLET: To eat: or not.")
    assert parsed.lines[0].character == "HAMLET"
    assert parsed.lines[0].dialogue == "To eat: or not."


def test_splitter_handles_accented_and_hyphenated_names():
    script = "JEAN-PAUL: Bonjour.\nÉLODIE: Salut.\nKING'S MESSENGER: Hail."
    parsed = split_script(script)
    chars = {line.character for line in parsed.lines}
    assert chars == {"JEAN-PAUL", "ÉLODIE", "KING'S MESSENGER"}


def test_splitter_assigns_stable_line_ids():
    parsed = split_script("HAMLET: One.\nGERTRUDE: Two.")
    ids = [line.line_id for line in parsed.lines]
    assert all(ids)
    assert len(set(ids)) == len(ids)


def test_splitter_marks_spoken_lines():
    parsed = split_script("HAMLET: Hi.")
    assert parsed.lines[0].spoken is True
    assert parsed.lines[0].text_only is False


def test_splitter_captures_standalone_stage_directions():
    parsed = split_script("(Thunder. They exit.)\nHAMLET: Alone at last.")
    # Direction is not a spoken line.
    assert [l.character for l in parsed.lines] == ["HAMLET"]
    assert len(parsed.directions) == 1
    assert parsed.directions[0].text_only is True
    assert parsed.directions[0].spoken is False


def test_splitter_rejected_details_have_reason_codes():
    parsed = split_script("random line that doesn't match\nHAMLET: ")
    reasons = {r.reason for r in parsed.rejected_details}
    assert "no_colon" in reasons
    assert "empty_dialogue" in reasons
