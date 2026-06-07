"""GUI tests for the consent modal."""
from __future__ import annotations

from hamlet_ai.consent import ConsentRecord
from hamlet_ai.gui.consent_dialog import ConsentDialog


def test_dialog_builds_consent_record(qtbot):
    dlg = ConsentDialog(volunteer_label="Burt")
    qtbot.addWidget(dlg)
    assert dlg.label_edit.text() == "Burt"
    record = dlg.consent_record()
    assert isinstance(record, ConsentRecord)
    assert record.volunteer_label == "Burt"
    assert record.confirmed_by_operator is True
    assert record.retention_policy == "keep"


def test_dialog_retention_selection(qtbot):
    dlg = ConsentDialog()
    qtbot.addWidget(dlg)
    # Pick "ephemeral" (index 1).
    dlg.retention_combo.setCurrentIndex(1)
    assert dlg.selected_retention() == "ephemeral"
    assert dlg.consent_record().retention_policy == "ephemeral"


def test_dialog_is_modal(qtbot):
    dlg = ConsentDialog()
    qtbot.addWidget(dlg)
    assert dlg.isModal() is True
