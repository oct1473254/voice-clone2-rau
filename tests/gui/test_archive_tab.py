"""GUI tests for the Archive tab (show-night rescue)."""
from __future__ import annotations

import pytest

from hamlet_ai.config import AppConfig, ScriptGenSettings, VoiceCloneSettings
from hamlet_ai.gui.voice_clone.archive_tab import ArchiveTab


@pytest.fixture(autouse=True)
def _no_modal(monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: QMessageBox.StandardButton.Ok)
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: QMessageBox.StandardButton.Ok)


@pytest.fixture
def cfg(tmp_path) -> AppConfig:
    return AppConfig(
        voice_clone=VoiceCloneSettings(base_dir=tmp_path / "VOICE-CLONE"),
        script_gen=ScriptGenSettings(base_dir=tmp_path / "LLM-H", workspace_dir=tmp_path / "ws"),
        dry_run=True,
    )


def _seed_archive(cfg, name, files):
    d = cfg.voice_clone.archive_dir / name
    d.mkdir(parents=True)
    for fn in files:
        (d / fn).write_bytes(b"x")
    return d


def test_lists_archives_newest_first(qtbot, cfg):
    _seed_archive(cfg, "20240101_000000", ["a.mp3"])
    _seed_archive(cfg, "20250101_000000", ["b.mp3"])
    tab = ArchiveTab(cfg)
    qtbot.addWidget(tab)
    assert tab.archive_list.item(0).text() == "20250101_000000"


def test_selecting_archive_lists_its_files(qtbot, cfg):
    _seed_archive(cfg, "20250101_000000", ["b.mp3", "c.mp3"])
    tab = ArchiveTab(cfg)
    qtbot.addWidget(tab)
    tab.archive_list.setCurrentRow(0)
    names = {tab.file_list.item(i).text() for i in range(tab.file_list.count())}
    assert names == {"b.mp3", "c.mp3"}


def test_restore_copies_archive_into_lines(qtbot, cfg):
    _seed_archive(cfg, "20250101_000000", ["ghost_00.mp3"])
    tab = ArchiveTab(cfg)
    qtbot.addWidget(tab)
    tab.archive_list.setCurrentRow(0)
    received = []
    tab.restored.connect(received.append)
    tab._on_restore()
    assert (cfg.voice_clone.lines_dir / "ghost_00.mp3").is_file()
    assert received == [1]
