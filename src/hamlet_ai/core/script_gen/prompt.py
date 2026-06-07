"""Scene-generation prompt construction, extracted from the legacy CLI.

The original ``Hamlet-gen5.construct_prompt`` interleaved user input directly
into the prompt template. We preserve the wording exactly so output quality
matches what the operator tested, but route the inputs through a
``ScriptGenParams`` dataclass so the GUI can validate fields before sending.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ScriptGenParams:
    play_name: str
    scene_name: str  # e.g. "Act II, Scene 1" or "ending"
    character_count: int  # 2..4
    character_name: str
    include: str  # person/place/event/thing
    style: str

    def validate(self) -> list[str]:
        errors: list[str] = []
        if not self.play_name.strip():
            errors.append("play_name is required")
        if not self.scene_name.strip():
            errors.append("scene_name is required")
        if self.character_count not in (2, 3, 4):
            errors.append("character_count must be 2, 3, or 4")
        if not self.character_name.strip():
            errors.append("character_name is required")
        if not self.include.strip():
            errors.append("include (person/place/event/thing) is required")
        if not self.style.strip():
            errors.append("style is required")
        return errors


def construct_prompt(params: ScriptGenParams) -> str:
    return f"""
    You are a talented and creative playwright. Write an alternate {params.scene_name} for {params.play_name}, the play by Shakespeare.
    The scene should be fifteen to thirty lines of dialogue long, written for {params.character_count} characters.
    Include {params.character_name.upper()} as a character; other character names should match the original scene.
    The format of the play MUST include the characters name in all caps followed by a colon. For example, HAMLET:
    The dialogue should be on the same line as the character name, with no line break.
    The first line should begin the dialogue, do not include any header information or any lines besides dialogue.
    The play should be in {params.style} style. You should incorporate {params.include} in the scene.
    There should be no stage directions, nor any parenthetical remarks that indicate line readings, e.g., (sadly).
    If more or fewer than {params.character_count} characters appear, rewrite so that exactly {params.character_count} characters appear in the final version.
    """
