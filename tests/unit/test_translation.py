"""Step 6: translation reuses the LLM dispatcher with cfg defaults."""
from __future__ import annotations

from types import SimpleNamespace

from hamlet_ai.config import AppConfig
from hamlet_ai.core.script_gen.llm import LLMClients
from hamlet_ai.core.script_gen.translation import translate


def test_translate_defaults_to_default_provider():
    cfg = AppConfig()
    cfg.script_gen.default_provider = "anthropic"
    cfg.anthropic_api_key = "an-key"

    captured = {}

    class StubAnthropic:
        def messages_create(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(content=[SimpleNamespace(text="Sein oder Nichtsein.")])

    def factory(api_key):
        captured["api_key"] = api_key
        return StubAnthropic()

    out = translate(
        "HAMLET: To be or not to be.",
        cfg,
        clients=LLMClients(anthropic_factory=factory),
    )
    assert out == "Sein oder Nichtsein."
    assert captured["api_key"] == "an-key"
    assert captured["model"] == "claude-sonnet-4-6"
    assert "German" in captured["messages"][0]["content"]


def test_translate_uses_translation_provider_when_set():
    cfg = AppConfig()
    cfg.script_gen.default_provider = "anthropic"
    cfg.script_gen.translation_provider = "openai"
    cfg.openai_api_key = "op-key"

    class StubOpenAI:
        def chat_create(self, **_):
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content="X"))]
            )

    def factory(api_key):
        assert api_key == "op-key"
        return StubOpenAI()

    out = translate("hi", cfg, clients=LLMClients(openai_factory=factory))
    assert out == "X"


def test_translate_respects_explicit_provider_and_model():
    cfg = AppConfig()
    cfg.script_gen.default_provider = "anthropic"
    cfg.anthropic_api_key = "an-key"

    captured = {}

    class StubAnthropic:
        def messages_create(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(content=[SimpleNamespace(text="ok")])

    translate(
        "hi",
        cfg,
        provider="anthropic",
        model="claude-opus-4-7",
        clients=LLMClients(anthropic_factory=lambda _: StubAnthropic()),
    )
    assert captured["model"] == "claude-opus-4-7"


def test_translate_supports_other_target_language():
    cfg = AppConfig()
    cfg.script_gen.default_provider = "anthropic"
    cfg.anthropic_api_key = "an-key"

    captured = {}

    class StubAnthropic:
        def messages_create(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(content=[SimpleNamespace(text="ok")])

    translate(
        "hi",
        cfg,
        target_language="French",
        clients=LLMClients(anthropic_factory=lambda _: StubAnthropic()),
    )
    assert "French" in captured["messages"][0]["content"]
