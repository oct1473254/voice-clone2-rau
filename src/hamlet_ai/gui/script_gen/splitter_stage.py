"""Splitter stage: run the tolerant splitter and show valid + rejected lines."""
from __future__ import annotations

from PySide6.QtCore import Signal, Slot
from PySide6.QtWidgets import (
    QLabel,
    QListWidget,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from hamlet_ai.config import AppConfig
from hamlet_ai.core.script_gen.line_splitter import split_script


class SplitterStage(QWidget):
    split_done = Signal(int)  # number of valid lines

    def __init__(self, cfg: AppConfig, state, parent: QWidget | None = None):
        super().__init__(parent)
        self.cfg = cfg
        self.state = state

        layout = QVBoxLayout(self)
        self.run_btn = QPushButton("Run Splitter")
        self.run_btn.clicked.connect(self.run_splitter)
        layout.addWidget(self.run_btn)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["line_id", "character", "dialogue", "spoken"])
        self.table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.table, stretch=2)

        layout.addWidget(QLabel("Rejected lines (reason):"))
        self.rejected_list = QListWidget()
        layout.addWidget(self.rejected_list, stretch=1)

    def on_enter(self) -> None:
        if self.state.english_text and self.state.parsed_en is None:
            self.run_splitter()

    @Slot()
    def run_splitter(self) -> None:
        parsed = split_script(self.state.english_text)
        self.state.parsed_en = parsed

        self.table.setRowCount(len(parsed.lines))
        for r, line in enumerate(parsed.lines):
            self.table.setItem(r, 0, QTableWidgetItem(line.line_id))
            self.table.setItem(r, 1, QTableWidgetItem(line.character))
            self.table.setItem(r, 2, QTableWidgetItem(line.dialogue))
            self.table.setItem(r, 3, QTableWidgetItem("yes" if line.spoken else "no"))

        self.rejected_list.clear()
        for rej in parsed.rejected_details:
            self.rejected_list.addItem(f"[{rej.reason}] {rej.raw}")

        self.split_done.emit(len(parsed.lines))
