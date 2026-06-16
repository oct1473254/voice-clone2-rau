"""Unit tests for the RunFolder per-run workspace."""
from __future__ import annotations


from hamlet_ai.core.voice_clone.runs import RunFolder


def test_create_for_now_lays_out_run_folder(cfg):
    run = RunFolder.create_for_now(cfg, now=0)
    assert run.root.is_dir()
    assert run.sample_dir.is_dir()
    assert run.generated_lines_dir.is_dir()
    assert run.log_path.is_file()
    # Lives under VOICE-CLONE/RUNS/
    assert run.root.parent == cfg.voice_clone.runs_dir


def test_create_for_now_avoids_collision(cfg):
    a = RunFolder.create_for_now(cfg, now=0)
    b = RunFolder.create_for_now(cfg, now=0)
    assert a.root != b.root


def test_copy_sample_in_copies_file(cfg, tmp_path):
    src = tmp_path / "vol.mp3"
    src.write_bytes(b"audio")
    run = RunFolder.create_for_now(cfg, now=0)
    dest = run.copy_sample_in(src)
    assert dest.is_file()
    assert dest.read_bytes() == b"audio"
    assert dest.parent == run.sample_dir
    # Source untouched.
    assert src.is_file()


def test_write_and_read_metadata_round_trip(cfg):
    run = RunFolder.create_for_now(cfg, now=0)
    run.write_metadata({"voice_id": "abc", "consent": {"volunteer_label": "Burt"}})
    assert run.metadata_path.is_file()
    meta = run.read_metadata()
    assert meta["voice_id"] == "abc"
    assert meta["consent"]["volunteer_label"] == "Burt"


def test_append_log_accumulates(cfg):
    run = RunFolder.create_for_now(cfg, now=0)
    run.append_log("line one")
    run.append_log("line two")
    text = run.log_path.read_text()
    assert "line one" in text
    assert "line two" in text


def test_metadata_write_is_atomic(cfg, monkeypatch):
    run = RunFolder.create_for_now(cfg, now=0)

    def boom(*a, **k):
        raise OSError("disk full")

    monkeypatch.setattr("os.replace", boom)
    try:
        run.write_metadata({"x": 1})
    except OSError:
        pass
    leftover = list(run.root.glob(".clone-meta-*"))
    assert leftover == [], f"temp files leaked: {leftover}"
