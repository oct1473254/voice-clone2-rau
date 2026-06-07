"""Step 4: ScriptDocument editing and round-trip with parse_script."""
from __future__ import annotations

import pytest

from hamlet_ai.core.voice_clone import pipeline
from hamlet_ai.core.voice_clone.script_model import ScriptDocument, ScriptEntry


def test_load_empty_file_returns_empty_list(tmp_path):
    doc = ScriptDocument(tmp_path / "clone.txt")
    assert doc.load() == []


def test_load_parses_filename_text_blocks(tmp_path):
    p = tmp_path / "clone.txt"
    p.write_text(
        "a.mp3\nHello\n\nb.mp3\nWorld\n",
        encoding="utf-8",
    )
    doc = ScriptDocument(p)
    entries = doc.load()
    assert [e.filename for e in entries] == ["a.mp3", "b.mp3"]
    assert [e.text for e in entries] == ["Hello", "World"]


def test_save_round_trips_through_parse_script(tmp_path):
    p = tmp_path / "clone.txt"
    doc = ScriptDocument(p)
    doc.save([
        ScriptEntry(filename="a.mp3", text="Hello [pause] world"),
        ScriptEntry(filename="b.mp3", text="Multi\nline\ntext"),
    ])
    parsed = pipeline.parse_script(p, log_fn=lambda *_: None)
    assert parsed == [
        ("a.mp3", "Hello [pause] world"),
        ("b.mp3", "Multi\nline\ntext"),
    ]


def test_update_insert_append_delete(tmp_path):
    doc = ScriptDocument(tmp_path / "clone.txt")
    doc.append(ScriptEntry("a.mp3", "Alpha"))
    doc.append(ScriptEntry("b.mp3", "Beta"))
    doc.append(ScriptEntry("c.mp3", "Gamma"))
    doc.update(1, ScriptEntry("b.mp3", "Beta2"))
    doc.insert(1, ScriptEntry("a2.mp3", "Alpha2"))
    doc.delete(0)
    assert [e.filename for e in doc.entries] == ["a2.mp3", "b.mp3", "c.mp3"]
    assert doc.entries[1].text == "Beta2"


def test_save_is_atomic(tmp_path, monkeypatch):
    p = tmp_path / "clone.txt"
    p.write_text("orig\n", encoding="utf-8")
    doc = ScriptDocument(p)
    doc.append(ScriptEntry("a.mp3", "Alpha"))

    def boom(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr("os.replace", boom)
    with pytest.raises(OSError):
        doc.save()
    assert p.read_text(encoding="utf-8") == "orig\n"
    assert list(tmp_path.glob(".clone-*")) == []
