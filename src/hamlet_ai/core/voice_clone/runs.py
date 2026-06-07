"""Per-run workspace under ``VOICE-CLONE/RUNS/{timestamp}/``.

Every voice-clone session gets its own isolated folder. The volunteer sample is
**copied** here (never moved out of ``SAMPLE/`` while the clone is in flight),
generated lines are written here first, and a ``clone_metadata.json`` +
``run_log.txt`` record what happened. This is the structural fix for the legacy
cleanup-during-clone race: the active sample is never relocated mid-clone.

All writes are atomic (``.tmp`` + ``os.replace``).
"""
from __future__ import annotations

import json
import os
import shutil
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

from hamlet_ai.config import AppConfig


@dataclass
class RunFolder:
    root: Path

    # ---- layout -----------------------------------------------------------
    @property
    def sample_dir(self) -> Path:
        return self.root / "sample"

    @property
    def generated_lines_dir(self) -> Path:
        return self.root / "generated_lines"

    @property
    def metadata_path(self) -> Path:
        return self.root / "clone_metadata.json"

    @property
    def log_path(self) -> Path:
        return self.root / "run_log.txt"

    # ---- construction -----------------------------------------------------
    @classmethod
    def create_for_now(cls, cfg: AppConfig, now: float | None = None) -> "RunFolder":
        ts = time.strftime("%Y%m%d_%H%M%S", time.localtime(now))
        root = cfg.voice_clone.runs_dir / ts
        # Avoid collision if two runs start in the same second.
        suffix = 1
        while root.exists():
            root = cfg.voice_clone.runs_dir / f"{ts}_{suffix}"
            suffix += 1
        run = cls(root=root)
        run.sample_dir.mkdir(parents=True, exist_ok=True)
        run.generated_lines_dir.mkdir(parents=True, exist_ok=True)
        run.log_path.touch()
        return run

    # ---- operations -------------------------------------------------------
    def copy_sample_in(self, src: Path) -> Path:
        """Copy ``src`` into this run's ``sample/`` and return the new path."""
        self.sample_dir.mkdir(parents=True, exist_ok=True)
        dest = self.sample_dir / src.name
        shutil.copy2(src, dest)
        return dest

    def write_metadata(self, data: dict) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(prefix=".clone-meta-", suffix=".json", dir=self.root)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(data, fh, indent=2, sort_keys=True)
            os.replace(tmp_name, self.metadata_path)
        except Exception:
            try:
                os.unlink(tmp_name)
            except FileNotFoundError:
                pass
            raise

    def read_metadata(self) -> dict:
        if not self.metadata_path.is_file():
            return {}
        try:
            return json.loads(self.metadata_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}

    def append_log(self, line: str) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        with open(self.log_path, "a", encoding="utf-8") as fh:
            fh.write(line.rstrip("\n") + "\n")
