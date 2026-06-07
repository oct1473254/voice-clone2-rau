"""Step 5: LLM dispatch with hand-rolled stub clients (no SDKs hit network)."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from hamlet_ai.config import AppConfig
from hamlet_ai.core.script_gen import llm as llm_mod
from hamlet_ai.core.script_gen.llm import (
    LLMClients,
    LLMError,
    LLMProvider,
    generate,
    generate_with_anthropic,
    generate_with_ollama,
    generate_with_openai,
)


# ---------- Anthropic ------------------------------------------------------

def test_generate_with_anthropic_extracts_text():
    class StubAnthropic:
        def messages_create(self, *, model, max_tokens, temperature, system, messages):
            assert model == "claude-sonnet-4-6"
            assert max_tokens == 1024
            assert temperature == 0
            assert "playwright" in system
            assert messages[0]["role"] == "user"
            return SimpleNamespace(content=[SimpleNamespace(text="ALAS, fair scene...")])

    text = generate_with_anthropic("the prompt", "claude-sonnet-4-6", StubAnthropic())
    assert text == "ALAS, fair scene..."


def test_generate_with_anthropic_raises_on_bad_response_shape():
    class StubAnthropic:
        def messages_create(self, **_):
            return SimpleNamespace(content=[])

    with pytest.raises(LLMError):
        generate_with_anthropic("p", "m", StubAnthropic())


# ---------- OpenAI ---------------------------------------------------------

def test_generate_with_openai_extracts_text():
    class StubOpenAI:
        def chat_create(self, *, model, messages):
            assert model == "gpt-4o"
            assert messages[0]["role"] == "system"
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content="HAMLET: Words, words."))]
            )

    text = generate_with_openai("the prompt", "gpt-4o", StubOpenAI())
    assert text.startswith("HAMLET:")


def test_generate_with_openai_raises_on_bad_response_shape():
    class StubOpenAI:
        def chat_create(self, **_):
            return SimpleNamespace(choices=[])

    with pytest.raises(LLMError):
        generate_with_openai("p", "m", StubOpenAI())


# ---------- Ollama --------------------------------------------------------

def test_generate_with_ollama_extracts_message_content():
    """Verifies the legacy ``response.completion`` bug is fixed."""

    class StubOllama:
        def chat(self, *, model, messages):
            assert model == "llama3.1"
            return {"message": {"role": "assistant", "content": "OPHELIA: I knew you not."}}

    text = generate_with_ollama("the prompt", "llama3.1", StubOllama())
    assert text == "OPHELIA: I knew you not."


def test_generate_with_ollama_raises_on_bad_response_shape():
    class StubOllama:
        def chat(self, **_):
            return {"completion": "wrong field"}

    with pytest.raises(LLMError):
        generate_with_ollama("p", "m", StubOllama())


# ---------- Dispatcher ---------------------------------------------------

def test_generate_dispatches_to_anthropic_via_clients():
    captured: dict[str, object] = {}

    class StubAnthropic:
        def messages_create(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(content=[SimpleNamespace(text="OK")])

    def factory(api_key):
        captured["api_key"] = api_key
        return StubAnthropic()

    out = generate(
        "prompt",
        LLMProvider.ANTHROPIC,
        "claude-sonnet-4-6",
        anthropic_api_key="an-key",
        clients=LLMClients(anthropic_factory=factory),
    )
    assert out == "OK"
    assert captured["api_key"] == "an-key"
    assert captured["model"] == "claude-sonnet-4-6"


def test_generate_dispatches_to_openai_via_clients():
    class StubOpenAI:
        def chat_create(self, **_):
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content="X"))]
            )

    def factory(api_key):
        assert api_key == "op-key"
        return StubOpenAI()

    out = generate(
        "p",
        "openai",
        "gpt-4o",
        openai_api_key="op-key",
        clients=LLMClients(openai_factory=factory),
    )
    assert out == "X"


def test_generate_dispatches_to_ollama_via_clients():
    class StubOllama:
        def chat(self, **_):
            return {"message": {"content": "Y"}}

    def factory():
        return StubOllama()

    out = generate(
        "p",
        "ollama",
        "llama3.1",
        clients=LLMClients(ollama_factory=factory),
    )
    assert out == "Y"


def test_generate_unknown_provider_raises():
    with pytest.raises(ValueError):
        generate("p", "made-up", "m")


# ---------- test_connection (Step 5) --------------------------------------

def _cfg_no_keys():
    return AppConfig(anthropic_api_key="an", openai_api_key="op")


def test_test_connection_anthropic_ok_records_health():
    cfg = _cfg_no_keys()

    class StubAnthropic:
        def messages_create(self, *, model, max_tokens, temperature, system, messages):
            assert max_tokens == 1
            return SimpleNamespace(content=[SimpleNamespace(text="pong")])

    ok, msg = llm_mod.test_connection(
        "anthropic", cfg, clients=LLMClients(anthropic_factory=lambda k: StubAnthropic())
    )
    assert ok is True
    assert "anthropic" in msg.lower()
    assert cfg.provider_health["anthropic"].status == "ok"
    assert cfg.provider_health["anthropic"].last_tested is not None


def test_test_connection_openai_failure_is_graceful():
    cfg = _cfg_no_keys()

    class StubOpenAI:
        def chat_create(self, **_):
            raise RuntimeError("401 Unauthorized")

    ok, msg = llm_mod.test_connection(
        "openai", cfg, clients=LLMClients(openai_factory=lambda k: StubOpenAI())
    )
    assert ok is False
    assert "openai" in msg.lower()
    assert cfg.provider_health["openai"].status == "failed"


def test_test_connection_ollama_ok_uses_list():
    cfg = _cfg_no_keys()
    called = {}

    class StubOllama:
        def chat(self, **_):  # should not be used
            raise AssertionError("chat must not be called in test_connection")

        def list(self):
            called["list"] = True
            return {"models": []}

    ok, msg = llm_mod.test_connection(
        "ollama", cfg, clients=LLMClients(ollama_factory=lambda: StubOllama())
    )
    assert ok is True
    assert called.get("list") is True


def test_test_connection_ollama_daemon_down_specific_message():
    cfg = _cfg_no_keys()

    class StubOllama:
        def list(self):
            raise ConnectionError("[Errno 61] Connection refused")

    ok, msg = llm_mod.test_connection(
        "ollama", cfg, clients=LLMClients(ollama_factory=lambda: StubOllama())
    )
    assert ok is False
    assert "daemon" in msg.lower()
    assert cfg.provider_health["ollama"].status == "failed"
