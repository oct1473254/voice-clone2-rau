"""Voice Library tab: list of recent volunteer clones."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt, Signal, Slot
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from hamlet_ai.config import AppConfig
from hamlet_ai.core.voice_clone.voice_library import VoiceEntry, VoiceLibrary


class _VoiceLibraryModel(QAbstractTableModel):
    HEADERS = ("Label", "Voice ID", "Created", "Sample")

    def __init__(self, entries: list[VoiceEntry], parent=None):
        super().__init__(parent)
        self.entries = entries

    def rowCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self.entries)

    def columnCount(self, parent=QModelIndex()) -> int:
        return len(self.HEADERS)

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role == Qt.DisplayRole and orientation == Qt.Horizontal:
            return self.HEADERS[section]
        return None

    def data(self, index: QModelIndex, role=Qt.DisplayRole) -> Any:
        if not index.isValid() or role != Qt.DisplayRole:
            return None
        e = self.entries[index.row()]
        return (e.label, e.voice_id, e.created_at, e.sample_filename)[index.column()]

    def entry_at(self, row: int) -> VoiceEntry:
        return self.entries[row]

    def reset_entries(self, entries: list[VoiceEntry]) -> None:
        self.beginResetModel()
        self.entries = entries
        self.endResetModel()


class VoiceLibraryTab(QWidget):
    active_voice_changed = Signal(str)  # voice_id
    play_requested = Signal(object)  # Path

    def __init__(self, cfg: AppConfig, library: VoiceLibrary | None = None, parent: QWidget | None = None):
        super().__init__(parent)
        self.cfg = cfg
        self.library = library or VoiceLibrary(cfg.voice_clone.voice_library_path)
        self.active_voice_id: str | None = None

        layout = QVBoxLayout(self)
        self.active_label = QLabel("Active voice: (none)")
        layout.addWidget(self.active_label)

        self.model = _VoiceLibraryModel(self.library.list())
        self.view = QTableView()
        self.view.setModel(self.model)
        self.view.horizontalHeader().setStretchLastSection(True)
        self.view.setSelectionBehavior(QTableView.SelectRows)
        self.view.setSelectionMode(QTableView.SingleSelection)
        layout.addWidget(self.view, stretch=1)

        row = QHBoxLayout()
        self.set_active_btn = QPushButton("Set as Active")
        self.set_active_btn.clicked.connect(self._on_set_active)
        row.addWidget(self.set_active_btn)
        self.play_btn = QPushButton("Play Sample")
        self.play_btn.clicked.connect(self._on_play)
        row.addWidget(self.play_btn)
        self.delete_btn = QPushButton("Delete")
        self.delete_btn.clicked.connect(self._on_delete)
        row.addWidget(self.delete_btn)
        layout.addLayout(row)

    def refresh(self) -> None:
        self.model.reset_entries(self.library.list())

    @Slot(object)
    def add_voice(self, entry: VoiceEntry) -> None:
        self.library.add(entry)
        self.refresh()

    def _selected_row(self) -> int | None:
        idx = self.view.currentIndex()
        if idx.isValid():
            return idx.row()
        return None

    @Slot()
    def _on_set_active(self) -> None:
        row = self._selected_row()
        if row is None:
            return
        entry = self.model.entry_at(row)
        self.active_voice_id = entry.voice_id
        self.active_label.setText(f"Active voice: {entry.label} ({entry.voice_id})")
        self.active_voice_changed.emit(entry.voice_id)

    @Slot()
    def _on_play(self) -> None:
        row = self._selected_row()
        if row is None:
            return
        path = Path(self.model.entry_at(row).sample_path)
        if path.exists():
            self.play_requested.emit(path)

    @Slot()
    def _on_delete(self) -> None:
        row = self._selected_row()
        if row is None:
            return
        entry = self.model.entry_at(row)
        self.library.remove(entry.voice_id)
        if self.active_voice_id == entry.voice_id:
            self.active_voice_id = None
            self.active_label.setText("Active voice: (none)")
        self.refresh()
