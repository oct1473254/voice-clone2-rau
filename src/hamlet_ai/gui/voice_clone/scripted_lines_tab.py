"""Scripted Lines tab: editable clone.txt + generate-all/selected with progress."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt, Signal, Slot
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from hamlet_ai.config import AppConfig
from hamlet_ai.core.voice_clone.script_model import ScriptDocument, ScriptEntry


class _ScriptModel(QAbstractTableModel):
    HEADERS = ("Filename", "Text", "Status")

    def __init__(self, doc: ScriptDocument, parent=None):
        super().__init__(parent)
        self.doc = doc
        self.entries: list[ScriptEntry] = list(doc.entries)
        # status per row: "" / "✓" / "✗"
        self.status: list[str] = [""] * len(self.entries)

    def rowCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self.entries)

    def columnCount(self, parent=QModelIndex()) -> int:
        return len(self.HEADERS)

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role == Qt.DisplayRole and orientation == Qt.Horizontal:
            return self.HEADERS[section]
        return None

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        if role not in (Qt.DisplayRole, Qt.EditRole):
            return None
        e = self.entries[index.row()]
        return (e.filename, e.text, self.status[index.row()])[index.column()]

    def setData(self, index, value, role=Qt.EditRole):
        if role != Qt.EditRole or not index.isValid():
            return False
        row, col = index.row(), index.column()
        old = self.entries[row]
        if col == 0:
            self.entries[row] = ScriptEntry(filename=str(value), text=old.text)
        elif col == 1:
            self.entries[row] = ScriptEntry(filename=old.filename, text=str(value))
        else:
            return False
        self.dataChanged.emit(index, index, [Qt.DisplayRole])
        return True

    def flags(self, index):
        if not index.isValid():
            return Qt.NoItemFlags
        base = Qt.ItemIsSelectable | Qt.ItemIsEnabled
        if index.column() in (0, 1):
            base |= Qt.ItemIsEditable
        return base

    def append_row(self, entry: ScriptEntry) -> None:
        self.beginInsertRows(QModelIndex(), len(self.entries), len(self.entries))
        self.entries.append(entry)
        self.status.append("")
        self.endInsertRows()

    def delete_row(self, row: int) -> None:
        self.beginRemoveRows(QModelIndex(), row, row)
        del self.entries[row]
        del self.status[row]
        self.endRemoveRows()

    def set_status(self, row: int, status: str) -> None:
        if 0 <= row < len(self.status):
            self.status[row] = status
            idx = self.index(row, 2)
            self.dataChanged.emit(idx, idx, [Qt.DisplayRole])

    def write_back(self) -> None:
        self.doc.save(self.entries)


class ScriptedLinesTab(QWidget):
    generate_requested = Signal(list)  # list[tuple[str, str]]

    def __init__(self, cfg: AppConfig, doc: ScriptDocument | None = None, parent: QWidget | None = None):
        super().__init__(parent)
        self.cfg = cfg
        self.doc = doc or ScriptDocument(cfg.voice_clone.script_file)
        try:
            self.doc.load()
        except FileNotFoundError:
            pass

        layout = QVBoxLayout(self)

        self.status_label = QLabel("Set an active voice in the Library tab before generating.")
        layout.addWidget(self.status_label)

        self.model = _ScriptModel(self.doc)
        self.view = QTableView()
        self.view.setModel(self.model)
        self.view.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.view, stretch=1)

        self.progress = QProgressBar()
        self.progress.setRange(0, 1)
        self.progress.setValue(0)
        layout.addWidget(self.progress)

        row = QHBoxLayout()
        self.add_btn = QPushButton("Add Row")
        self.add_btn.clicked.connect(self._on_add)
        row.addWidget(self.add_btn)
        self.delete_btn = QPushButton("Delete Row")
        self.delete_btn.clicked.connect(self._on_delete)
        row.addWidget(self.delete_btn)
        self.save_btn = QPushButton("Save clone.txt")
        self.save_btn.clicked.connect(self._on_save)
        row.addWidget(self.save_btn)
        self.generate_all_btn = QPushButton("Generate All")
        self.generate_all_btn.setEnabled(False)
        self.generate_all_btn.clicked.connect(self._on_generate_all)
        row.addWidget(self.generate_all_btn)
        self.generate_selected_btn = QPushButton("Generate Selected")
        self.generate_selected_btn.setEnabled(False)
        self.generate_selected_btn.clicked.connect(self._on_generate_selected)
        row.addWidget(self.generate_selected_btn)
        layout.addLayout(row)

    @Slot(str)
    def set_active_voice(self, voice_id: str | None) -> None:
        enabled = bool(voice_id)
        self.generate_all_btn.setEnabled(enabled)
        self.generate_selected_btn.setEnabled(enabled)
        if voice_id:
            self.status_label.setText(f"Active voice: {voice_id}")

    def _on_add(self) -> None:
        self.model.append_row(ScriptEntry(filename="new_line.mp3", text="Enter dialogue."))

    def _on_delete(self) -> None:
        idx = self.view.currentIndex()
        if idx.isValid():
            self.model.delete_row(idx.row())

    def _on_save(self) -> None:
        self.model.write_back()
        self.status_label.setText(f"Saved {len(self.model.entries)} lines to {self.doc.path}.")

    def _on_generate_all(self) -> None:
        self._on_save()
        self._emit_generate(list(enumerate(self.model.entries)))

    def _on_generate_selected(self) -> None:
        idx = self.view.currentIndex()
        if not idx.isValid():
            return
        self._on_save()
        row = idx.row()
        self._emit_generate([(row, self.model.entries[row])])

    def _emit_generate(self, rows: list[tuple[int, ScriptEntry]]) -> None:
        self.progress.setRange(0, len(rows))
        self.progress.setValue(0)
        self._pending_rows = [r for r, _ in rows]
        lines = [(e.filename, e.text) for _, e in rows]
        self.generate_requested.emit(lines)

    @Slot(int, int)
    def on_progress(self, done: int, total: int) -> None:
        self.progress.setRange(0, total)
        self.progress.setValue(done)

    @Slot(str, object)
    def on_line_done(self, filename: str, path: Path) -> None:
        for i, entry in enumerate(self.model.entries):
            if entry.filename == filename:
                self.model.set_status(i, "✓")
                return
