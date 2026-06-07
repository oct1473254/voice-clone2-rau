"""Unit tests for the first-run inventory + backup migration."""
from __future__ import annotations

import json
from pathlib import Path

from hamlet_ai.config import AppConfig
from hamlet_ai import migration


def test_take_inventory_on_empty_workspaces(cfg: AppConfig):
    inv = migration.take_inventory(cfg)
    assert set(inv.directories) == {"voice_clone", "script_gen"}
    vc = inv.directories["voice_clone"]
    # ensure_dirs (from the cfg fixture) created the dirs but they're empty.
    assert vc.exists is True
    assert vc.file_count == 0
    assert vc.has_clone_txt is False
    assert vc.archive_count == 0
    assert vc.stale_samples == []


def test_inventory_counts_files_clone_txt_archives_and_stale_samples(
    cfg: AppConfig, fake_clone_txt: Path, fake_sample_audio: Path
):
    # Add an archive subfolder with a file in it.
    archive_sub = cfg.voice_clone.archive_dir / "20240101_000000"
    archive_sub.mkdir(parents=True)
    (archive_sub / "ghost_old.mp3").write_bytes(b"x")

    vc = migration.inventory_dir(
        cfg.voice_clone.base_dir,
        clone_txt=cfg.voice_clone.script_file,
        archive_dir=cfg.voice_clone.archive_dir,
        sample_dir=cfg.voice_clone.sample_dir,
    )
    assert vc.has_clone_txt is True
    assert vc.clone_txt_path == str(cfg.voice_clone.script_file)
    assert vc.archive_count == 1
    assert "volunteer.mp3" in vc.stale_samples
    assert vc.file_count >= 3  # clone.txt + sample + archived file


def test_count_files_ignores_hidden(cfg: AppConfig):
    d = cfg.voice_clone.base_dir
    (d / "visible.txt").write_text("x")
    (d / ".hidden").write_text("x")
    assert migration._count_files(d) == 1


def test_backup_dir_copies_existing_nonempty(cfg: AppConfig, fake_clone_txt: Path):
    dest = migration.backup_dir(cfg.voice_clone.base_dir, now=0)
    assert dest is not None
    assert dest.is_dir()
    assert dest.name.startswith("VOICE-CLONE.backup-")
    # The clone.txt should have been copied across.
    assert (dest / "SCRIPT" / "clone.txt").is_file()


def test_backup_dir_skips_missing_or_empty(tmp_path: Path):
    missing = tmp_path / "nope"
    assert migration.backup_dir(missing) is None

    empty = tmp_path / "empty"
    empty.mkdir()
    assert migration.backup_dir(empty) is None


def test_first_run_writes_inventory_json_and_is_idempotent(
    cfg: AppConfig, fake_clone_txt: Path, tmp_path: Path
):
    inv_path = tmp_path / "config" / "first_run_inventory.json"
    assert migration.has_completed_first_run(inv_path) is False

    result = migration.run_first_run_migration(cfg, inventory_path=inv_path)
    assert result is not None
    assert inv_path.is_file()
    assert migration.has_completed_first_run(inv_path) is True

    payload = json.loads(inv_path.read_text())
    assert "created_at" in payload
    assert payload["directories"]["voice_clone"]["has_clone_txt"] is True

    # Second call is a no-op (returns None, doesn't re-backup).
    second = migration.run_first_run_migration(cfg, inventory_path=inv_path)
    assert second is None


def test_first_run_records_backup_paths(
    cfg: AppConfig, fake_clone_txt: Path, tmp_path: Path
):
    inv_path = tmp_path / "first_run_inventory.json"
    result = migration.run_first_run_migration(
        cfg, inventory_path=inv_path, do_backup=True, now=0
    )
    assert result is not None
    assert result.backups["voice_clone"] is not None
    assert Path(result.backups["voice_clone"]).is_dir()
    # LLM-H is empty in the fixture → no backup.
    assert result.backups["script_gen"] is None


def test_force_reruns_even_after_completion(cfg: AppConfig, tmp_path: Path):
    inv_path = tmp_path / "first_run_inventory.json"
    migration.run_first_run_migration(cfg, inventory_path=inv_path, do_backup=False)
    forced = migration.run_first_run_migration(
        cfg, inventory_path=inv_path, do_backup=False, force=True
    )
    assert forced is not None
