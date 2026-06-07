"""Archive tab — browse past runs and restore LINES/ (the show-night rescue).

Lists ``ARCHIVE/{ts}/`` subfolders newest-first; selecting one shows its files
with per-row Play. "Restore last good LINES/" copies the selected archive back
into ``LINES/`` (atomic per file) so a botched live run can be recovered fast.
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from hamlet_ai.config import AppConfig
from hamlet_ai.core.voice_clone.pipeline import restore_last_good


class ArchiveTab(QWidget):
    play_requested = Signal(object)  # Path
    restored = Signal(int)  # number of files restored

    def __init__(self, cfg: AppConfig, parent: QWidget | None = None):
        super().__init__(parent)
        self.cfg = cfg

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Archived runs (newest first):"))

        body = QHBoxLayout()
        self.archive_list = QListWidget()
        self.archive_list.currentRowChanged.connect(self._on_archive_selected)
        body.addWidget(self.archive_list, stretch=1)
        self.file_list = QListWidget()
        body.addWidget(self.file_list, stretch=1)
        layout.addLayout(body)

        row = QHBoxLayout()
        self.play_btn = QPushButton("Play Selected File")
        self.play_btn.clicked.connect(self._on_play)
        row.addWidget(self.play_btn)
        self.restore_btn = QPushButton("Restore last good LINES/")
        self.restore_btn.clicked.connect(self._on_restore)
        row.addWidget(self.restore_btn)
        layout.addLayout(row)

        self.refresh()

    def _archive_dirs(self) -> list[Path]:
        d = self.cfg.voice_clone.archive_dir
        if not d.is_dir():
            return []
        return sorted((p for p in d.iterdir() if p.is_dir()), key=lambda p: p.name, reverse=True)

    def refresh(self) -> None:
        self.archive_list.clear()
        self.file_list.clear()
        for p in self._archive_dirs():
            self.archive_list.addItem(p.name)
        if self.archive_list.count():
            self.archive_list.setCurrentRow(0)

    @Slot(int)
    def _on_archive_selected(self, row: int) -> None:
        self.file_list.clear()
        dirs = self._archive_dirs()
        if not (0 <= row < len(dirs)):
            return
        for f in sorted(dirs[row].iterdir()):
            if f.is_file() and not f.name.startswith("."):
                self.file_list.addItem(f.name)

    def _selected_archive(self) -> Path | None:
        dirs = self._archive_dirs()
        row = self.archive_list.currentRow()
        return dirs[row] if 0 <= row < len(dirs) else None

    @Slot()
    def _on_play(self) -> None:
        archive = self._selected_archive()
        item = self.file_list.currentItem()
        if archive is None or item is None:
            return
        path = archive / item.text()
        if path.exists():
            self.play_requested.emit(path)

    @Slot()
    def _on_restore(self) -> None:
        archive = self._selected_archive()
        if archive is None:
            QMessageBox.warning(self, "Restore", "No archive selected.")
            return
        try:
            restored = restore_last_good(self.cfg, archive_name=archive.name, log_fn=lambda *_: None)
        except FileNotFoundError as e:
            QMessageBox.warning(self, "Restore failed", str(e))
            return
        self.restored.emit(len(restored))
        QMessageBox.information(self, "Restore complete", f"Restored {len(restored)} file(s) to LINES/.")
