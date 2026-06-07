"""Unit tests for log redaction."""
from __future__ import annotations

from hamlet_ai.redaction import redact


def test_redacts_explicit_secret():
    out = redact("connecting with el-key-secret now", secrets=["el-key-secret"])
    assert "el-key-secret" not in out
    assert "<REDACTED>" in out


def test_redacts_known_key_shapes():
    # Keys long enough to match the redactor (16+) but short of the secrets-guard
    # threshold (32+) so this test file itself stays clean.
    assert "sk_" not in redact("key=sk_" + "a" * 20)
    assert "sk-ant-" not in redact("key=sk-ant-" + "b" * 20)


def test_volunteer_label_masked_only_in_show_mode():
    msg = "cloned voice for Audience Burt"
    assert "Audience Burt" in redact(msg, volunteer_labels=["Audience Burt"], show_mode=False)
    masked = redact(msg, volunteer_labels=["Audience Burt"], show_mode=True)
    assert "Audience Burt" not in masked
    assert "<volunteer>" in masked


def test_none_passes_through():
    assert redact(None) is None
