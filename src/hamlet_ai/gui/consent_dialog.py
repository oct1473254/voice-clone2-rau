"""Blocking consent modal shown before the first clone of a volunteer.

The operator must explicitly confirm the volunteer consented. The dialog
produces a :class:`hamlet_ai.consent.ConsentRecord` carrying the chosen
retention policy, which the pipeline writes into the RunFolder metadata.
"""
from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QLabel,
    QLineEdit,
    QVBoxLayout,
    QWidget,
)

from hamlet_ai.consent import ConsentRecord, new_consent

CONSENT_TEXT = (
    "This records the volunteer, uploads the sample to ElevenLabs, creates a "
    "voice clone, and generates lines in that voice.\n\n"
    "Tap Confirm only if the volunteer has consented to this."
)

_RETENTION_LABELS = [
    ("keep", "Keep (default)"),
    ("ephemeral", "Ephemeral — delete at end of session"),
    ("delete_after_show", "Delete after show (TTL sweep)"),
]


class ConsentDialog(QDialog):
    def __init__(self, volunteer_label: str = "", parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("Volunteer Consent")
        self.setModal(True)

        layout = QVBoxLayout(self)
        msg = QLabel(CONSENT_TEXT)
        msg.setWordWrap(True)
        layout.addWidget(msg)

        layout.addWidget(QLabel("Volunteer label:"))
        self.label_edit = QLineEdit(volunteer_label or "volunteer")
        layout.addWidget(self.label_edit)

        layout.addWidget(QLabel("Retention policy:"))
        self.retention_combo = QComboBox()
        for value, text in _RETENTION_LABELS:
            self.retention_combo.addItem(text, value)
        layout.addWidget(self.retention_combo)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Ok
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Confirm")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def selected_retention(self) -> str:
        return self.retention_combo.currentData()

    def consent_record(self) -> ConsentRecord:
        """Build the ConsentRecord from the dialog's current fields."""
        return new_consent(
            self.label_edit.text().strip() or "volunteer",
            self.selected_retention(),
        )
