"""Hamlet.AI unified CLI.

Subcommands:
    gui           Launch the PySide6 application.
    voice-clone   Run the voice-clone pipeline (legacy voiceclone2.py behavior).
    script-gen    Run the Shakespeare scene generator (legacy Hamlet-gen5.py behavior).
"""
from __future__ import annotations

import argparse
import sys
from typing import Sequence

from hamlet_ai.config import AppConfig, default_config, ensure_dirs


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="hamlet-ai",
        description="Voice clone + Shakespeare scene generation for Wember/Wolf359.",
    )
    sub = parser.add_subparsers(dest="command", metavar="COMMAND")

    sub.add_parser("gui", help="Launch the PySide6 GUI.")
    sub.add_parser("doctor", help="Run pre-show health checks and print a report.")

    vc = sub.add_parser("voice-clone", help="Run the voice-clone pipeline.")
    vc.add_argument(
        "--dry-run",
        action="store_true",
        help="Skip ElevenLabs API calls; write placeholders instead.",
    )
    vc.add_argument(
        "--volunteer",
        default="volunteer",
        help="Label for the volunteer whose voice is cloned.",
    )
    vc.add_argument(
        "--i-consent",
        action="store_true",
        help="Operator attests the volunteer consented to being recorded and cloned (required).",
    )
    vc.add_argument(
        "--retention",
        choices=("keep", "ephemeral", "delete_after_show"),
        default="keep",
        help="Retention policy for the cloned voice.",
    )

    sg = sub.add_parser("script-gen", help="Generate the German Hamlet ghost scene.")
    sg.add_argument("--interactive", action="store_true", help="Prompt for inputs (legacy behavior).")
    sg.add_argument("--character-one", default="Ophelia", help="First extra character (default: Ophelia).")
    sg.add_argument("--character-two", default="Horatio", help="Second extra character (default: Horatio).")
    sg.add_argument("--setting", default="", help="Optional setting to set in / mention (blank = LLM chooses).")
    sg.add_argument("--llm", choices=("anthropic", "openai", "ollama"), help="LLM provider.")
    sg.add_argument(
        "--no-translate",
        action="store_true",
        help="Skip the English review translation step.",
    )
    sg.add_argument(
        "--no-tts",
        action="store_true",
        help="Skip the per-line TTS step (write text files only).",
    )
    sg.add_argument(
        "--dry-run",
        action="store_true",
        help="Skip ElevenLabs API calls (TTS produces placeholder files).",
    )

    return parser


def _run_doctor(cfg: AppConfig) -> int:
    from hamlet_ai.doctor import format_report, run_checks

    ensure_dirs(cfg)
    report = run_checks(cfg)
    print(format_report(report))
    return report.exit_code


def _run_voice_clone(args: argparse.Namespace, cfg: AppConfig) -> int:
    from hamlet_ai.consent import ConsentNotProvided, new_consent
    from hamlet_ai.core.voice_clone.pipeline import run_show

    if args.dry_run:
        cfg.dry_run = True
    ensure_dirs(cfg)

    if not args.i_consent:
        print(
            "❌ voice-clone requires --i-consent: the operator must attest that the "
            "volunteer consented to being recorded and cloned.",
            file=sys.stderr,
        )
        return 2
    consent = new_consent(args.volunteer, args.retention)

    try:
        run_show(cfg, consent=consent)
    except ConsentNotProvided as e:
        print(f"❌ {e}", file=sys.stderr)
        return 2
    except (FileNotFoundError, RuntimeError, TimeoutError) as e:
        print(f"❌ voice-clone failed: {e}", file=sys.stderr)
        return 1
    return 0


def _gather_script_gen_params(args: argparse.Namespace):
    from hamlet_ai.core.script_gen.prompt import ScriptGenParams

    if args.interactive:
        character_one = input("First extra character [Ophelia]: ").strip() or "Ophelia"
        character_two = input("Second extra character [Horatio]: ").strip() or "Horatio"
        setting = input("Optional setting to set in / mention (blank = LLM chooses): ").strip()
        return ScriptGenParams(
            character_one=character_one,
            character_two=character_two,
            setting=setting,
        )
    return ScriptGenParams(
        character_one=args.character_one,
        character_two=args.character_two,
        setting=args.setting,
    )


def _run_script_gen(args: argparse.Namespace, cfg: AppConfig) -> int:
    from hamlet_ai.core.script_gen.character_voices import CharacterVoiceMap
    from hamlet_ai.core.script_gen.export import copy_to_desktop
    from hamlet_ai.core.script_gen.line_splitter import split_script, write_split_files
    from hamlet_ai.core.script_gen.llm import LLMProvider, generate
    from hamlet_ai.core.script_gen.prompt import construct_prompt
    from hamlet_ai.core.script_gen.translation import (
        TranslationCountMismatch,
        translate_scene,
    )
    from hamlet_ai.core.script_gen.tts import synthesize_line

    if args.dry_run:
        cfg.dry_run = True
    if args.llm:
        cfg.script_gen.default_provider = args.llm

    try:
        params = _gather_script_gen_params(args)
    except SystemExit as e:
        print(e, file=sys.stderr)
        return 2

    errors = params.validate()
    if errors:
        for e in errors:
            print(f"❌ {e}", file=sys.stderr)
        return 2

    ensure_dirs(cfg)
    workspace = cfg.script_gen.workspace_dir
    provider = LLMProvider(cfg.script_gen.default_provider)
    model = cfg.script_gen.models[provider.value]

    print(f"🎭 Generating German scene via {provider.value} ({model})...")
    prompt = construct_prompt(params, cfg.script_gen.prompt_template)
    try:
        german = generate(
            prompt,
            provider,
            model,
            anthropic_api_key=cfg.anthropic_api_key,
            openai_api_key=cfg.openai_api_key,
        )
    except Exception as e:  # noqa: BLE001 — surface any SDK error to the operator
        print(f"❌ LLM generation failed: {e}", file=sys.stderr)
        return 1

    de_path = workspace / "german_scene.txt"
    de_path.parent.mkdir(parents=True, exist_ok=True)
    de_path.write_text(german, encoding="utf-8")
    print(f"📝 German scene saved: {de_path}")

    # German is the performed language. Split it first, then translate
    # line-by-line into English so each review line stays aligned to its German
    # character label and line_id (instead of translating + re-splitting, which
    # can drift).
    parsed_de = split_script(german, allowed=params.allowed_characters())
    write_split_files(parsed_de, workspace, language="German")
    print(f"🪓 Split {len(parsed_de.lines)} German lines.")
    print("--- German scene ---")
    for line in parsed_de.lines:
        print(f"{line.character}: {line.dialogue}")

    if not args.no_translate:
        print("🌍 Translating to English for review (per line)...")
        try:
            parsed_en = translate_scene(parsed_de, cfg, target_language="English")
        except TranslationCountMismatch as e:
            print(f"⚠️  English translation skipped (line count mismatch): {e}", file=sys.stderr)
            parsed_en = None
        except Exception as e:  # noqa: BLE001
            print(f"⚠️  English translation failed: {e}", file=sys.stderr)
            parsed_en = None
        if parsed_en is not None:
            en_text = "\n".join(
                f"{line.character}: {line.dialogue}" for line in parsed_en.lines
            )
            en_path = workspace / "english_scene.txt"
            en_path.write_text(en_text, encoding="utf-8")
            print(f"📝 English scene saved: {en_path}")
            write_split_files(parsed_en, workspace, language="English")
            print(f"🪓 Split {len(parsed_en.lines)} English lines.")
            print("--- English translation ---")
            print(en_text)

    if not args.no_tts:
        voice_map = CharacterVoiceMap(cfg.script_gen.character_voices_path)
        de_output = workspace / "valid_lines" / "German" / "output"
        de_output.mkdir(parents=True, exist_ok=True)
        print(f"🔊 Synthesizing {len(parsed_de.lines)} German lines...")
        for i, line in enumerate(parsed_de.lines, start=1):
            voice_id = voice_map.resolve(line.character)
            out = de_output / f"{line.line_number:03d}-{line.character}.mp3"
            try:
                synthesize_line(cfg, line.dialogue, voice_id, out)
            except Exception as e:  # noqa: BLE001 — keep going on per-line failure
                print(f"   ❌ Line {i}: {e}", file=sys.stderr)
        print("🔊 TTS complete.")

    print(f"📦 Copying to Desktop layout: {cfg.script_gen.base_dir}")
    copy_to_desktop(workspace, cfg.script_gen.base_dir)
    print("🎭 Done.")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command is None:
        parser.print_help()
        return 0

    # Load ELEVENLABS_API_KEY / provider keys from a project-root .env so all
    # subcommands (gui, doctor, voice-clone, script-gen) pick them up, matching
    # the legacy shims and the .command launcher. Existing env vars win.
    from dotenv import load_dotenv

    load_dotenv()

    cfg = default_config()

    if args.command == "gui":
        from hamlet_ai.gui.app import run as run_gui
        return run_gui()

    if args.command == "doctor":
        return _run_doctor(cfg)

    if args.command == "voice-clone":
        return _run_voice_clone(args, cfg)

    if args.command == "script-gen":
        return _run_script_gen(args, cfg)

    parser.error(f"unknown command: {args.command}")
    return 2


def entrypoint() -> None:
    raise SystemExit(main())
