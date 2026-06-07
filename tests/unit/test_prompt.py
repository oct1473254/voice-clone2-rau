"""Step 5: ScriptGenParams + construct_prompt."""
from __future__ import annotations

import pytest

from hamlet_ai.core.script_gen.prompt import ScriptGenParams, construct_prompt


def _valid() -> ScriptGenParams:
    return ScriptGenParams(
        play_name="Hamlet",
        scene_name="Act II, Scene 1",
        character_count=3,
        character_name="Polonius",
        include="a hidden microphone",
        style="absurdist",
    )


def test_validate_returns_empty_for_valid_params():
    assert _valid().validate() == []


def test_validate_reports_each_missing_field():
    bad = ScriptGenParams("", "", 1, "", "", "")
    errors = bad.validate()
    assert any("play_name" in e for e in errors)
    assert any("scene_name" in e for e in errors)
    assert any("character_count" in e for e in errors)
    assert any("character_name" in e for e in errors)
    assert any("include" in e for e in errors)
    assert any("style" in e for e in errors)


@pytest.mark.parametrize("count", [2, 3, 4])
def test_validate_accepts_supported_character_counts(count):
    p = _valid()
    p.character_count = count
    assert p.validate() == []


@pytest.mark.parametrize("count", [0, 1, 5, 10])
def test_validate_rejects_out_of_range_character_counts(count):
    p = _valid()
    p.character_count = count
    errors = p.validate()
    assert any("character_count" in e for e in errors)


def test_construct_prompt_includes_required_pieces():
    params = _valid()
    prompt = construct_prompt(params)
    assert "Hamlet" in prompt
    assert "Act II, Scene 1" in prompt
    assert "POLONIUS" in prompt  # upper-cased per template
    assert "absurdist" in prompt
    assert "a hidden microphone" in prompt
    assert "3 characters" in prompt
    assert "no stage directions" in prompt
