"""QApplication bootstrap. Called by ``hamlet-ai gui``."""
from __future__ import annotations

import logging
import sys
import traceback
from pathlib import Path

from PySide6.QtWidgets import QApplication

from hamlet_ai.config import SETTINGS_PATH_DEFAULT, default_config, ensure_dirs
from hamlet_ai.gui.main_window import MainWindow
from hamlet_ai.migration import run_first_run_migration

# When the GUI is double-clicked from a file manager there is no terminal, so an
# uncaught exception (e.g. a failed save) vanishes and the app just "misbehaves".
# Mirror every uncaught exception to a logfile next to settings.json so it can be
# recovered after the fact.
LOG_PATH = SETTINGS_PATH_DEFAULT.parent / "hamlet-ai.log"


def _install_crash_logging() -> Path:
    """Route uncaught exceptions to ``LOG_PATH`` (and stderr). Returns the path."""
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        filename=str(LOG_PATH),
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    def _hook(exc_type, exc, tb):
        logging.error("Uncaught exception:\n%s", "".join(traceback.format_exception(exc_type, exc, tb)))
        sys.__excepthook__(exc_type, exc, tb)

    sys.excepthook = _hook
    return LOG_PATH


def run() -> int:
    _install_crash_logging()
    logging.info("Starting Hamlet.AI GUI")
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
