"""First-run inventory + backup of the existing on-disk workspaces.

Before the unified app ever writes into ``~/Desktop/VOICE-CLONE/`` or
``~/Desktop/LLM-H/`` it takes a snapshot of whatever the legacy scripts left
behind and (optionally) makes a timestamped backup copy so nothing the operator
already produced can be silently clobbered.

The three first-run actions (per the implementation plan):
  (a) inventory both workspaces — file counts, ``clone.txt`` presence, archive
      count, and any stale samples sitting in ``SAMPLE/``;
  (b) write a timestamped backup copy of each existing workspace to
      ``<dir>.backup-{ts}/`` *before* any clobbering write;
  (c) record the inventory in ``~/.config/hamlet-ai/first_run_inventory.json``.

Importing this module has no side effects. Everything is driven by an explicit
``AppConfig`` so tests can point it at ``tmp_path``.
"""
from __future__ import annotations

import json
import os
import shutil
import tempfile
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from hamlet_ai.config import AppConfig


INVENTORY_PATH_DEFAULT = Path.home() / ".config" / "hamlet-ai" / "first_run_inventory.json"


@dataclass
class DirInventory:
    """Snapshot of a single workspace directory."""

    path: str
    exists: bool
    file_count: int
    has_clone_txt: bool
    clone_txt_path: str | None
    archive_count: int
    stale_samples: list[str] = field(default_factory=list)


@dataclass
class FirstRunInventory:
    created_at: str  # ISO 8601 UTC
    directories: dict[str, DirInventory]
    backups: dict[str, str | None]

    def to_dict(self) -> dict:
        return {
            "created_at": self.created_at,
            "directories": {k: asdict(v) for k, v in self.directories.items()},
            "backups": dict(self.backups),
        }


# ---------- inventory ------------------------------------------------------

def _count_files(directory: Path) -> int:
    """Recursively count non-hidden files under ``directory`` (0 if absent)."""
    if not directory.is_dir():
        return 0
    total = 0
    for root, dirs, files in os.walk(directory):
        # Skip hidden directories in-place so os.walk doesn't descend into them.
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        total += sum(1 for f in files if not f.startswith("."))
    return total


def _visible_files(directory: Path) -> list[str]:
    if not directory.is_dir():
        return []
    return sorted(
        f.name for f in directory.iterdir() if f.is_file() and not f.name.startswith(".")
    )


def inventory_dir(
    base_dir: Path,
    *,
    clone_txt: Path | None = None,
    archive_dir: Path | None = None,
    sample_dir: Path | None = None,
) -> DirInventory:
    """Build a :class:`DirInventory` for ``base_dir``.

    ``clone_txt``/``archive_dir``/``sample_dir`` are optional sub-paths that are
    only meaningful for the VOICE-CLONE workspace; pass ``None`` for LLM-H.
    """
    exists = base_dir.is_dir()
    has_clone_txt = bool(clone_txt and clone_txt.is_file())
    archive_count = 0
    if archive_dir and archive_dir.is_dir():
        archive_count = sum(1 for p in archive_dir.iterdir() if p.is_dir())
    stale_samples = _visible_files(sample_dir) if sample_dir else []

    return DirInventory(
        path=str(base_dir),
        exists=exists,
        file_count=_count_files(base_dir),
        has_clone_txt=has_clone_txt,
        clone_txt_path=str(clone_txt) if has_clone_txt else None,
        archive_count=archive_count,
        stale_samples=stale_samples,
    )


def take_inventory(cfg: AppConfig) -> FirstRunInventory:
    """Inventory both workspaces. Performs no writes and no backups."""
    vc = cfg.voice_clone
    voice_clone = inventory_dir(
        vc.base_dir,
        clone_txt=vc.script_file,
        archive_dir=vc.archive_dir,
        sample_dir=vc.sample_dir,
    )
    script_gen = inventory_dir(cfg.script_gen.base_dir)
    return FirstRunInventory(
        created_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        directories={"voice_clone": voice_clone, "script_gen": script_gen},
        backups={"voice_clone": None, "script_gen": None},
    )


# ---------- backup ---------------------------------------------------------

def backup_dir(src: Path, now: float | None = None) -> Path | None:
    """Copy ``src`` to a sibling ``<name>.backup-{ts}/``. Returns the dest, or
    ``None`` if ``src`` doesn't exist or is empty.
    """
    if not src.is_dir():
        return None
    if _count_files(src) == 0:
        return None
    ts = time.strftime("%Y%m%d_%H%M%S", time.localtime(now))
    dest = src.parent / f"{src.name}.backup-{ts}"
    # Avoid collision if two backups land in the same second.
    suffix = 1
    while dest.exists():
        dest = src.parent / f"{src.name}.backup-{ts}_{suffix}"
        suffix += 1
    shutil.copytree(src, dest)
    return dest


# ---------- persistence ----------------------------------------------------

def has_completed_first_run(inventory_path: Path | None = None) -> bool:
    path = inventory_path or INVENTORY_PATH_DEFAULT
    return path.is_file()


def _write_inventory_json(inventory: FirstRunInventory, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=".first-run-", suffix=".json", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(inventory.to_dict(), fh, indent=2, sort_keys=True)
        os.replace(tmp_name, path)
    except Exception:
        try:
            os.unlink(tmp_name)
        except FileNotFoundError:
            pass
        raise


# ---------- orchestration --------------------------------------------------

def run_first_run_migration(
    cfg: AppConfig,
    *,
    inventory_path: Path | None = None,
    do_backup: bool = True,
    force: bool = False,
    now: float | None = None,
) -> FirstRunInventory | None:
    """Run the one-time first-run migration.

    Returns the :class:`FirstRunInventory` that was recorded, or ``None`` if the
    migration had already run (and ``force`` is False).
    """
    path = inventory_path or INVENTORY_PATH_DEFAULT
    if not force and has_completed_first_run(path):
        return None

    inventory = take_inventory(cfg)

    if do_backup:
        vc_backup = backup_dir(cfg.voice_clone.base_dir, now=now)
        sg_backup = backup_dir(cfg.script_gen.base_dir, now=now)
        inventory.backups["voice_clone"] = str(vc_backup) if vc_backup else None
        inventory.backups["script_gen"] = str(sg_backup) if sg_backup else None

    _write_inventory_json(inventory, path)
    return inventory
