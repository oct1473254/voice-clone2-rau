"""Scene-generation prompt construction.

The operator-supplied creative brief reimagines Hamlet's ghost scene in a
Pulitzer style, generated **in German**. Three inputs vary per run — the two
extra characters (Ophelia/Horatio by default, editable) and an optional
setting — and are injected into the prompt via the placeholder tokens
``{character_one}``, ``{character_two}`` and ``{setting_clause}``.

The full prompt text lives in :data:`DEFAULT_PROMPT_TEMPLATE` so the operator can
override it from the GUI's **Prompt** tab (persisted in config as
``ScriptGenSettings.prompt_template``). A blank/unset override falls back to the
default. The template has two parts: the creative brief, kept **verbatim** so
output quality matches what the operator tested, and a short *formatting*
paragraph so the generated scene is machine-parseable (``CHARACTER: dialogue``
per line) — the splitter and per-line TTS downstream depend on that shape.
Editing the formatting rules out of a custom template will break voicing.
"""
from __future__ import annotations

from dataclasses import dataclass


# The default scene-generation prompt, as a single editable string. The three
# ``{...}`` tokens are filled per run by ``construct_prompt``; everything else is
# sent to the LLM verbatim. The blank line separates the creative brief from the
# technical formatting scaffolding the downstream splitter/TTS require.
DEFAULT_PROMPT_TEMPLATE = (
    "You are a Pulitzer prize winning playwright who reexamines the classics. "
    "rewrite the ghost scene from Hamlet but more relevant to 2026, and make it "
    "less sexist, and less boring. Your script should be a maximum of one page. "
    "There should no stage directions, except for entrances and and no line "
    "reading to the actors. Make the dialogue contemporary, taking inspiration "
    "from John Guare, Eugene O’Neill, Jose Rivera, Brandon jacobs jenkins. "
    "The scene should include in addition to hamlet and the Ghost, two "
    "characters, {character_one} and {character_two}. "
    "The scene must contain ONLY these four characters — Hamlet, the Ghost, "
    "{character_one}, and {character_two}. Do not invent, name, mention, or "
    "give dialogue to any other character (no servants, messengers, friends, "
    "narrators, or crowds). {setting_clause} "
    "Please reply with only the scene no commentary. "
    "Please generate the scene in German language."
    "\n\n"
    "Format every spoken line as the speaking character's name in CAPITAL "
    "LETTERS, followed by a colon and a space, then that character's words on "
    "the same line, for example:\n"
    "HAMLET: ...\n"
    "Put each spoken line on its own line. Write any entrance on its own line "
    "in square brackets, for example: [OPHELIA tritt auf]. Do not include any "
    "other stage directions, parenthetical line readings, headings, or "
    "commentary."
)


@dataclass
class ScriptGenParams:
    # The two extra characters alongside Hamlet and the Ghost. Pre-filled but
    # editable; the setting is optional (blank → the playwright chooses one).
    character_one: str = "Ophelia"
    character_two: str = "Horatio"
    setting: str = ""

    def validate(self) -> list[str]:
        errors: list[str] = []
        if not self.character_one.strip():
            errors.append("character_one is required")
        if not self.character_two.strip():
            errors.append("character_two is required")
        # setting is intentionally optional — blank lets the LLM choose.
        return errors

    def allowed_characters(self) -> list[str]:
        """The only characters a generated scene may contain.

        Hamlet, the Ghost (rendered ``GEIST`` in the German output — both
        spellings are listed so the splitter's case/accent-insensitive match
        accepts either), and the two operator-chosen characters. ``split_script``
        rejects any speaker outside this set, enforcing the four-character cap
        even when the LLM ignores the prompt and invents extras.
        """
        return [
            "Hamlet",
            "Ghost",
            "Geist",
            self.character_one.strip(),
            self.character_two.strip(),
        ]


def construct_prompt(params: ScriptGenParams, template: str | None = None) -> str:
    """Render the scene-generation prompt for ``params``.

    ``template`` is the raw prompt text with ``{character_one}``,
    ``{character_two}`` and ``{setting_clause}`` tokens; pass the operator's
    override (``cfg.script_gen.prompt_template``) here. A blank/None template
    falls back to :data:`DEFAULT_PROMPT_TEMPLATE`. Tokens are filled by literal
    replacement (not ``str.format``) so stray braces in a hand-edited template
    can never raise; unknown tokens are simply left untouched.
    """
    setting = params.setting.strip()
    setting_clause = (
        f"It should be set in, or mention, {setting}."
        if setting
        else (
            "It should be set in, or mention, a contemporary place and moment of "
            "your choosing that suits the reimagining."
        )
    )

    text = template if (template and template.strip()) else DEFAULT_PROMPT_TEMPLATE
    return (
        text.replace("{character_one}", params.character_one.strip())
        .replace("{character_two}", params.character_two.strip())
        .replace("{setting_clause}", setting_clause)
    )
