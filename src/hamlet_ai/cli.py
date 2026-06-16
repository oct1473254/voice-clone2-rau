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

    sg = sub.add_parser("script-gen", help="Generate a Shakespeare-style scene.")
    sg.add_argument("--interactive", action="store_true", help="Prompt for inputs (legacy behavior).")
    sg.add_argument("--play", help="Shakespeare play name.")
    sg.add_argument("--scene", help="Scene label, e.g. 'Act II, Scene 1' or 'ending'.")
    sg.add_argument("--character-count", type=int, choices=range(2, 5), help="Number of characters (2-4).")
    sg.add_argument("--character-name", help="Required character to include.")
    sg.add_argument("--include", help="Person/place/event/thing to incorporate.")
    sg.add_argument("--style", help="Dialogue style.")
    sg.add_argument("--llm", choices=("anthropic", "openai", "ollama"), help="LLM provider.")
    sg.add_argument(
        "--no-translate",
        action="store_true",
        help="Skip the German translation step.",
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
        play_name = input("Please enter the name of a Shakespeare play: ")
        scene_name = input("Please enter 'ending', or the Act and Scene as in 'Act X, Scene Y': ")
        character_count = int(input("Please enter number of characters, from 2 - 4: "))
        character_name = input("Please enter the name a character to include: ")
        include = input("Please enter a person, place, event, or thing to incorporate: ")
        style = input("Please enter the style of the dialogue: ")
        return ScriptGenParams(
            play_name=play_name,
            scene_name=scene_name,
            character_count=character_count,
            character_name=character_name,
            include=include,
            style=style,
        )
    required = ("play", "scene", "character_count", "character_name", "include", "style")
    missing = [r for r in required if getattr(args, r) in (None, "")]
    if missing:
        raise SystemExit(
            f"❌ script-gen requires --interactive or all of: {', '.join('--' + r.replace('_', '-') for r in required)}"
        )
    return ScriptGenParams(
        play_name=args.play,
        scene_name=args.scene,
        character_count=args.character_count,
        character_name=args.character_name,
        include=args.include,
        style=args.style,
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

    print(f"🎭 Generating scene via {provider.value} ({model})...")
    prompt = construct_prompt(params)
    try:
        english = generate(
            prompt,
            provider,
            model,
            anthropic_api_key=cfg.anthropic_api_key,
            openai_api_key=cfg.openai_api_key,
        )
    except Exception as e:  # noqa: BLE001 — surface any SDK error to the operator
        print(f"❌ LLM generation failed: {e}", file=sys.stderr)
        return 1

    en_path = workspace / "english_scene.txt"
    en_path.parent.mkdir(parents=True, exist_ok=True)
    en_path.write_text(english, encoding="utf-8")
    print(f"📝 English scene saved: {en_path}")

    # Split English first, then translate line-by-line. This keeps each German
    # line aligned to its English character label and line_id (Step 6) instead
    # of translating the whole scene and re-splitting, which can drift.
    parsed_en = split_script(english)
    write_split_files(parsed_en, workspace, language="English")
    print(f"🪓 Split {len(parsed_en.lines)} English lines.")

    parsed_de = None
    if not args.no_translate:
        print("🌍 Translating to German (per line)...")
        try:
            parsed_de = translate_scene(parsed_en, cfg, target_language="German")
        except TranslationCountMismatch as e:
            print(f"⚠️  Translation skipped (line count mismatch): {e}", file=sys.stderr)
            parsed_de = None
        except Exception as e:  # noqa: BLE001
            print(f"⚠️  Translation failed: {e}", file=sys.stderr)
            parsed_de = None
        if parsed_de is not None:
            de_text = "\n".join(
                f"{line.character}: {line.dialogue}" for line in parsed_de.lines
            )
            de_path = workspace / "german_scene.txt"
            de_path.write_text(de_text, encoding="utf-8")
            print(f"📝 German scene saved: {de_path}")
            write_split_files(parsed_de, workspace, language="German")
            print(f"🪓 Split {len(parsed_de.lines)} German lines.")

    if not args.no_tts:
        voice_map = CharacterVoiceMap(cfg.script_gen.character_voices_path)
        en_output = workspace / "valid_lines" / "English" / "output"
        en_output.mkdir(parents=True, exist_ok=True)
        print(f"🔊 Synthesizing {len(parsed_en.lines)} English lines...")
        for i, line in enumerate(parsed_en.lines, start=1):
            voice_id = voice_map.resolve(line.character)
            out = en_output / f"{line.line_number:03d}-{line.character}.mp3"
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
