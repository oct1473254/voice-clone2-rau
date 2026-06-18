"""ScriptGenParams + construct_prompt: the fixed German ghost-scene brief."""
from __future__ import annotations

from hamlet_ai.core.script_gen.prompt import (
    DEFAULT_PROMPT_TEMPLATE,
    ScriptGenParams,
    construct_prompt,
)


def test_defaults_are_ophelia_and_horatio():
    p = ScriptGenParams()
    assert p.character_one == "Ophelia"
    assert p.character_two == "Horatio"
    assert p.setting == ""


def test_validate_returns_empty_for_default_params():
    assert ScriptGenParams().validate() == []


def test_validate_reports_blank_characters():
    errors = ScriptGenParams(character_one="", character_two="  ").validate()
    assert any("character_one" in e for e in errors)
    assert any("character_two" in e for e in errors)


def test_validate_allows_blank_setting():
    assert ScriptGenParams(setting="").validate() == []


def test_construct_prompt_includes_creative_brief_and_characters():
    prompt = construct_prompt(ScriptGenParams(character_one="Ophelia", character_two="Horatio"))
    assert "Pulitzer" in prompt
    assert "ghost scene from Hamlet" in prompt
    assert "2026" in prompt
    assert "Ophelia" in prompt
    assert "Horatio" in prompt
    # Always generates German.
    assert "German language" in prompt
    # Machine-format scaffolding so the splitter/TTS can parse it.
    assert "CAPITAL" in prompt and "HAMLET:" in prompt


def test_construct_prompt_substitutes_custom_characters_and_setting():
    prompt = construct_prompt(
        ScriptGenParams(character_one="Marcellus", character_two="Bernardo", setting="a Berlin U-Bahn platform")
    )
    assert "Marcellus" in prompt
    assert "Bernardo" in prompt
    assert "a Berlin U-Bahn platform" in prompt


def test_construct_prompt_blank_setting_leaves_choice_to_llm():
    prompt = construct_prompt(ScriptGenParams(setting=""))
    assert "of your choosing" in prompt


def test_custom_template_fills_placeholder_tokens():
    template = "Scene with {character_one} and {character_two}. {setting_clause}"
    prompt = construct_prompt(
        ScriptGenParams(character_one="A", character_two="B", setting="Mars"),
        template,
    )
    assert prompt == "Scene with A and B. It should be set in, or mention, Mars."


def test_blank_template_falls_back_to_default():
    a = construct_prompt(ScriptGenParams(), "")
    b = construct_prompt(ScriptGenParams(), None)
    c = construct_prompt(ScriptGenParams(), "   ")
    assert a == b == c
    assert "Pulitzer" in a


def test_custom_template_with_stray_braces_does_not_raise():
    # A hand-edited template may contain stray/unknown braces; literal replacement
    # must leave them untouched rather than raising (unlike str.format).
    prompt = construct_prompt(ScriptGenParams(), "stray { brace and {unknown}")
    assert prompt == "stray { brace and {unknown}"


def test_default_template_constant_renders_to_known_prompt():
    rendered = construct_prompt(ScriptGenParams(), DEFAULT_PROMPT_TEMPLATE)
    assert rendered == construct_prompt(ScriptGenParams())
