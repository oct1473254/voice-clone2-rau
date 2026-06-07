"""QApplication bootstrap. Called by ``hamlet-ai gui``."""
from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from hamlet_ai.config import default_config, ensure_dirs
from hamlet_ai.gui.main_window import MainWindow


def run() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    cfg = default_config()
    ensure_dirs(cfg)
    window = MainWindow(cfg)
    window.show()
    return app.exec()
