"""Translation of a generated scene into another language via the LLM dispatcher."""
from __future__ import annotations

from hamlet_ai.config import AppConfig
from hamlet_ai.core.script_gen.llm import LLMClients, LLMProvider, generate


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
