"""Global Qt stylesheet for Hamlet.AI.

Kept in one place so the backstage look (large, color-coded primary buttons;
readable headings) is consistent across tabs. Objects opt in via ``objectName``:
``bigRecordButton``, ``transportButton``, ``cloneButton``, ``generateButton``,
and the ``recordHeading`` / ``sgHeading`` section titles.
"""
from __future__ import annotations

GLOBAL_STYLESHEET = """
QLabel#recordHeading, QLabel#sgHeading {
    font-size: 20px;
    font-weight: 700;
    padding-bottom: 4px;
}

QPushButton#bigRecordButton {
    background-color: #c62828;
    color: white;
    font-size: 26px;
    font-weight: 800;
    border: none;
    border-radius: 10px;
}
QPushButton#bigRecordButton:hover { background-color: #d32f2f; }
QPushButton#bigRecordButton:disabled { background-color: #8a8a8a; color: #e0e0e0; }

QPushButton#transportButton {
    font-size: 16px;
    font-weight: 600;
    border-radius: 8px;
}

QPushButton#cloneButton {
    background-color: #1565c0;
    color: white;
    font-weight: 700;
    padding: 8px 14px;
    border: none;
    border-radius: 8px;
}
QPushButton#cloneButton:hover { background-color: #1976d2; }
QPushButton#cloneButton:disabled { background-color: #b0bec5; color: #eceff1; }

QPushButton#generateButton {
    background-color: #6a1b9a;
    color: white;
    font-size: 20px;
    font-weight: 800;
    border: none;
    border-radius: 10px;
}
QPushButton#generateButton:hover { background-color: #7b1fa2; }
QPushButton#generateButton:disabled { background-color: #b39ddb; color: #f3e5f5; }
"""
