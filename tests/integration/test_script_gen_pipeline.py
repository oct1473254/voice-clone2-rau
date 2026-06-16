"""Integration: prompt → LLM (German) → split → translate (English) → TTS → export.

German is the performed/voiced language; English is a review translation.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock


from hamlet_ai.core.elevenlabs import ElevenLabsClient
from hamlet_ai.core.script_gen.character_voices import CharacterVoiceMap
from hamlet_ai.core.script_gen.export import copy_to_desktop
from hamlet_ai.core.script_gen.line_splitter import split_script, write_split_files
from hamlet_ai.core.script_gen.llm import LLMClients, generate
from hamlet_ai.core.script_gen.prompt import ScriptGenParams, construct_prompt
from hamlet_ai.core.script_gen.translation import translate
from hamlet_ai.core.script_gen.tts import synthesize_line


GERMAN_SCENE = (
    "HAMLET: Worte, Worte, Worte.\n"
    "GERTRUDE: Sprich nicht weiter, suesser Sohn.\n"
    "GEIST: Wenn dies Wahnsinn ist, so hat er doch Methode.\n"
)
ENGLISH_SCENE = (
    "HAMLET: Words, words, words.\n"
    "GERTRUDE: Speak no more, sweet son.\n"
    "GEIST: Though this be madness, yet there is method.\n"
)


def test_script_gen_end_to_end_dry_run(cfg, tmp_path):
    """Full pipeline runs against mocked LLM stubs and DRY_RUN ElevenLabs."""
    cfg.dry_run = True
    cfg.script_gen.default_provider = "anthropic"
    cfg.anthropic_api_key = "stub"
    workspace = cfg.script_gen.workspace_dir

    # 1. Prompt construction — the fixed German ghost-scene brief.
    params = ScriptGenParams(character_one="Ophelia", character_two="Horatio")
    assert params.validate() == []
    prompt = construct_prompt(params)
    assert "German language" in prompt

    # 2. LLM generation — stubbed, returns the German scene
    class StubAnthropic:
        def __init__(self, payload: str):
            self.payload = payload

        def messages_create(self, **_):
            return SimpleNamespace(content=[SimpleNamespace(text=self.payload)])

    gen_clients = LLMClients(anthropic_factory=lambda _: StubAnthropic(GERMAN_SCENE))
    german = generate(prompt, "anthropic", cfg.script_gen.models["anthropic"], anthropic_api_key="stub", clients=gen_clients)
    assert german == GERMAN_SCENE

    # 3. Translation to English for review — stubbed
    trans_clients = LLMClients(anthropic_factory=lambda _: StubAnthropic(ENGLISH_SCENE))
    english = translate(german, cfg, target_language="English", clients=trans_clients)
    assert "Words" in english

    # 4. Line splitting + filesystem writes for both languages
    parsed_de = split_script(german)
    parsed_en = split_script(english)
    assert parsed_de.characters == ["GEIST", "GERTRUDE", "HAMLET"]
    write_split_files(parsed_de, workspace, language="German")
    write_split_files(parsed_en, workspace, language="English")

    # 5. TTS for each German line, DRY_RUN → placeholder files
    voice_map = CharacterVoiceMap(cfg.script_gen.character_voices_path)
    de_output_dir = workspace / "valid_lines" / "German" / "output"
    for line in parsed_de.lines:
        voice_id = voice_map.resolve(line.character)
        out = de_output_dir / f"{line.line_number:03d}-{line.character}.mp3"
        synthesize_line(cfg, line.dialogue, voice_id, out, log_fn=lambda *_: None)
        assert out.is_file()

    # 6. Export → copy (not move) to Desktop layout
    desktop = tmp_path / "MockDesktop" / "LLM-H"
    paths = copy_to_desktop(workspace, desktop, log_fn=lambda *_: None)
    assert (paths["audio"] / "001-HAMLET.mp3").is_file()
    assert (paths["text_german"] / "001-HAMLET.txt").is_file()
    assert (paths["text_english"] / "001-HAMLET.txt").is_file()
    assert (paths["names"] / "01-GEIST.txt").is_file()
    # Workspace is preserved
    assert (workspace / "valid_lines" / "German" / "001-HAMLET.txt").is_file()


def test_script_gen_uses_real_elevenlabs_client_when_not_dry_run(cfg, tmp_path):
    """Per-line synthesize routes through the injected ElevenLabsClient."""
    cfg.dry_run = False
    client = MagicMock(spec=ElevenLabsClient)
    client.synthesize.return_value = b"\x00MP3"

    workspace = cfg.script_gen.workspace_dir
    parsed = split_script("HAMLET: Hallo.\nGERTRUDE: Guten Tag.\n")
    write_split_files(parsed, workspace, language="German")

    de_output = workspace / "valid_lines" / "German" / "output"
    de_output.mkdir(parents=True, exist_ok=True)
    for line in parsed.lines:
        out = de_output / f"{line.line_number:03d}-{line.character}.mp3"
        synthesize_line(cfg, line.dialogue, "voice-x", out, log_fn=lambda *_: None, client=client)
        assert out.read_bytes() == b"\x00MP3"

    assert client.synthesize.call_count == 2
