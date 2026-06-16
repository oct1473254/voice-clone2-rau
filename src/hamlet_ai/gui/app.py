"""QApplication bootstrap. Called by ``hamlet-ai gui``."""
from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from hamlet_ai.config import default_config, ensure_dirs
from hamlet_ai.gui.main_window import MainWindow
from hamlet_ai.migration import run_first_run_migration


def run() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    cfg = default_config()
    # One-time inventory + backup of any existing Desktop artifacts before we
    # create/clobber anything. Idempotent and best-effort — never block launch.
    try:
        run_first_run_migration(cfg)
    except Exception:  # noqa: BLE001
        pass
    ensure_dirs(cfg)
    window = MainWindow(cfg)
    window.show()
    return app.exec()
