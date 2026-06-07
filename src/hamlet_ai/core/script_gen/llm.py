"""LLM provider dispatch.

Wraps the three SDKs (Anthropic, OpenAI, Ollama) behind a single
``generate(prompt, provider, model)`` entry point. SDK clients are constructed
lazily via injectable factories so tests can swap in hand-rolled stubs without
needing the real packages.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Protocol


class LLMProvider(str, Enum):
    ANTHROPIC = "anthropic"
    OPENAI = "openai"
    OLLAMA = "ollama"


class LLMError(RuntimeError):
    pass


# ---------- Protocols (so tests can pass duck-typed stubs) ----------------

class AnthropicLike(Protocol):
    def messages_create(self, *, model: str, max_tokens: int, temperature: float, system: str, messages: list[dict]) -> Any: ...


class OpenAILike(Protocol):
    def chat_create(self, *, model: str, messages: list[dict]) -> Any: ...


class OllamaLike(Protocol):
    def chat(self, *, model: str, messages: list[dict]) -> dict: ...


# ---------- Factories (default implementations build real SDK clients) ----

def _build_anthropic(api_key: str | None) -> AnthropicLike:
    import anthropic

    raw = anthropic.Anthropic(api_key=api_key) if api_key else anthropic.Anthropic()

    class _Adapter:
        def messages_create(self, *, model, max_tokens, temperature, system, messages):
            return raw.messages.create(
                model=model,
                max_tokens=max_tokens,
                temperature=temperature,
                system=system,
                messages=messages,
            )

    return _Adapter()


def _build_openai(api_key: str | None) -> OpenAILike:
    from openai import OpenAI

    raw = OpenAI(api_key=api_key) if api_key else OpenAI()

    class _Adapter:
        def chat_create(self, *, model, messages):
            return raw.chat.completions.create(model=model, messages=messages)

    return _Adapter()


def _build_ollama() -> OllamaLike:
    import ollama

    class _Adapter:
        def chat(self, *, model, messages):
            return ollama.chat(model=model, messages=messages)

    return _Adapter()


# ---------- Per-provider generation ---------------------------------------

def generate_with_anthropic(prompt: str, model: str, client: AnthropicLike) -> str:
    response = client.messages_create(
        model=model,
        max_tokens=1024,
        temperature=0,
        system="You are a world-class playwright.",
        messages=[{"role": "user", "content": prompt}],
    )
    try:
        return response.content[0].text  # type: ignore[attr-defined]
    except (AttributeError, IndexError, KeyError) as e:
        raise LLMError(f"unexpected Anthropic response shape: {e}") from e


def generate_with_openai(prompt: str, model: str, client: OpenAILike) -> str:
    response = client.chat_create(
        model=model,
        messages=[
            {"role": "system", "content": "You are a talented and creative playwright."},
            {"role": "user", "content": prompt},
        ],
    )
    try:
        return response.choices[0].message.content  # type: ignore[attr-defined]
    except (AttributeError, IndexError, KeyError) as e:
        raise LLMError(f"unexpected OpenAI response shape: {e}") from e


def generate_with_ollama(prompt: str, model: str, client: OllamaLike) -> str:
    response = client.chat(model=model, messages=[{"role": "user", "content": prompt}])
    # Fix the legacy ``response.completion`` bug — correct field is message.content
    try:
        return response["message"]["content"]
    except (KeyError, TypeError) as e:
        raise LLMError(f"unexpected Ollama response shape: {e}") from e


# ---------- Dispatcher ----------------------------------------------------

@dataclass
class LLMClients:
    """Bundle of optional client factories. None → build the real SDK client lazily."""
    anthropic_factory: Callable[[str | None], AnthropicLike] | None = None
    openai_factory: Callable[[str | None], OpenAILike] | None = None
    ollama_factory: Callable[[], OllamaLike] | None = None


def generate(
    prompt: str,
    provider: LLMProvider | str,
    model: str,
    *,
    anthropic_api_key: str | None = None,
    openai_api_key: str | None = None,
    clients: LLMClients | None = None,
) -> str:
    """Run a single completion against the chosen provider. Returns text."""
    provider = LLMProvider(provider)
    clients = clients or LLMClients()
    if provider is LLMProvider.ANTHROPIC:
        factory = clients.anthropic_factory or _build_anthropic
        return generate_with_anthropic(prompt, model, factory(anthropic_api_key))
    if provider is LLMProvider.OPENAI:
        factory = clients.openai_factory or _build_openai
        return generate_with_openai(prompt, model, factory(openai_api_key))
    if provider is LLMProvider.OLLAMA:
        factory = clients.ollama_factory or _build_ollama
        return generate_with_ollama(prompt, model, factory())
    raise LLMError(f"unknown provider: {provider}")
