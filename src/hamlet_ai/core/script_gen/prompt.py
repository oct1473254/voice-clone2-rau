"""Scene-generation prompt construction.

The operator-supplied creative brief is fixed: a Pulitzer-style reimagining of
Hamlet's ghost scene, generated **in German**. Only three inputs vary — the two
extra characters (Ophelia/Horatio by default, editable) and an optional setting.

The creative paragraph is kept **verbatim** so output quality matches what the
operator tested. We append a short, separate *formatting* paragraph so the
generated scene is machine-parseable (``CHARACTER: dialogue`` per line) — the
splitter and per-line TTS downstream depend on that shape. Without it nothing
could be voiced.
"""
from __future__ import annotations

from dataclasses import dataclass


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


def construct_prompt(params: ScriptGenParams) -> str:
    setting = params.setting.strip()
    setting_clause = (
        f"It should be set in, or mention, {setting}."
        if setting
        else (
            "It should be set in, or mention, a contemporary place and moment of "
            "your choosing that suits the reimagining."
        )
    )
    character_one = params.character_one.strip()
    character_two = params.character_two.strip()

    creative = (
        "You are a Pulitzer prize winning playwright who reexamines the classics. "
        "rewrite the ghost scene from Hamlet but more relevant to 2026, and make it "
        "less sexist, and less boring. Your script should be a maximum of one page. "
        "There should no stage directions, except for entrances and and no line "
        "reading to the actors. Make the dialogue contemporary, taking inspiration "
        "from John Guare, Eugene O’Neill, Jose Rivera, Brandon jacobs jenkins. "
        "The scene should include in addition to hamlet and the Ghost, two "
        f"characters, {character_one} and {character_two}. "
        "The scene must contain ONLY these four characters — Hamlet, the Ghost, "
        f"{character_one}, and {character_two}. Do not invent, name, mention, or "
        "give dialogue to any other character (no servants, messengers, friends, "
        f"narrators, or crowds). {setting_clause} "
        "Please reply with only the scene no commentary. "
        "Please generate the scene in German language."
    )

    # Technical formatting scaffolding (not part of the creative brief). Required
    # so split_script() can parse speakers and per-line TTS can voice each line.
    formatting = (
        "Format every spoken line as the speaking character's name in CAPITAL "
        "LETTERS, followed by a colon and a space, then that character's words on "
        "the same line, for example:\n"
        "HAMLET: ...\n"
        "Put each spoken line on its own line. Write any entrance on its own line "
        "in square brackets, for example: [OPHELIA tritt auf]. Do not include any "
        "other stage directions, parenthetical line readings, headings, or "
        "commentary."
    )

    return f"{creative}\n\n{formatting}"
