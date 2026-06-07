"""Translation of a generated scene into another language via the LLM dispatcher."""
from __future__ import annotations

import re
from dataclasses import replace

from hamlet_ai.config import AppConfig
from hamlet_ai.core.script_gen.line_splitter import ParsedScript, ScriptLine
from hamlet_ai.core.script_gen.llm import LLMClients, LLMProvider, generate


class TranslationCountMismatch(RuntimeError):
    """Raised when a per-line translation returns a different number of lines."""

    def __init__(self, expected: int, got: int):
        super().__init__(
            f"translation returned {got} dialogue lines, expected {expected}"
        )
        self.expected = expected
        self.got = got


def translate(
    text: str,
    cfg: AppConfig,
    *,
    target_language: str = "German",
    provider: LLMProvider | str | None = None,
    model: str | None = None,
    clients: LLMClients | None = None,
) -> str:
    """Translate ``text`` into ``target_language``.

    ``provider`` defaults to ``cfg.script_gen.translation_provider`` if set,
    otherwise ``cfg.script_gen.default_provider``. ``model`` resolves from
    ``cfg.script_gen.models[provider]``.
    """
    resolved_provider = (
        provider
        or cfg.script_gen.translation_provider
        or cfg.script_gen.default_provider
    )
    provider_enum = LLMProvider(resolved_provider)
    resolved_model = model or cfg.script_gen.models[provider_enum.value]

    prompt = (
        f"Translate the following Shakespearean dialogue into {target_language}. "
        f"Preserve the CHARACTER: dialogue line format. Do not add commentary.\n\n"
        f"{text}"
    )
    return generate(
        prompt,
        provider_enum,
        resolved_model,
        anthropic_api_key=cfg.anthropic_api_key,
        openai_api_key=cfg.openai_api_key,
        clients=clients,
    )


_NUM_PREFIX_RE = re.compile(r"^\s*\d+[.)]\s*")


def _strip_dialogue(raw: str) -> str:
    """From a translated ``N. CHARACTER: dialogue`` line, return just the dialogue."""
    without_num = _NUM_PREFIX_RE.sub("", raw).strip()
    if ":" in without_num:
        return without_num.split(":", 1)[1].strip()
    return without_num


def translate_scene(
    parsed: ParsedScript,
    cfg: AppConfig,
    target_language: str = "German",
    *,
    provider: LLMProvider | str | None = None,
    model: str | None = None,
    clients: LLMClients | None = None,
) -> ParsedScript:
    """Translate a :class:`ParsedScript` dialogue line-by-line.

    The character labels and ``line_id``s are preserved verbatim; only each
    line's dialogue is translated. The number of returned lines must match the
    input or :class:`TranslationCountMismatch` is raised so the GUI can warn.
    Stage directions are carried through untranslated.
    """
    if not parsed.lines:
        return replace(parsed)

    resolved_provider = (
        provider
        or cfg.script_gen.translation_provider
        or cfg.script_gen.default_provider
    )
    provider_enum = LLMProvider(resolved_provider)
    resolved_model = model or cfg.script_gen.models[provider_enum.value]

    numbered = "\n".join(
        f"{i + 1}. {line.character}: {line.dialogue}"
        for i, line in enumerate(parsed.lines)
    )
    prompt = (
        f"Translate the dialogue below into {target_language}.\n"
        f"Rules:\n"
        f"- Output exactly one line per input line, same numbering.\n"
        f"- Keep the leading number and the CHARACTER: prefix verbatim; translate "
        f"only the words spoken after the colon.\n"
        f"- Do not merge, split, add, or drop lines. Do not add commentary.\n\n"
        f"{numbered}"
    )
    response = generate(
        prompt,
        provider_enum,
        resolved_model,
        anthropic_api_key=cfg.anthropic_api_key,
        openai_api_key=cfg.openai_api_key,
        clients=clients,
    )

    out_raw = [ln for ln in response.splitlines() if ln.strip()]
    if len(out_raw) != len(parsed.lines):
        raise TranslationCountMismatch(len(parsed.lines), len(out_raw))

    new_lines: list[ScriptLine] = [
        replace(orig, dialogue=_strip_dialogue(raw))
        for orig, raw in zip(parsed.lines, out_raw)
    ]
    return replace(parsed, lines=new_lines)
