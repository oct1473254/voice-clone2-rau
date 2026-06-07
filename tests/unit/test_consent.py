"""Unit tests for consent records and the consent gate."""
from __future__ import annotations

import pytest

from hamlet_ai.consent import (
    ConsentNotProvided,
    ConsentRecord,
    new_consent,
    require_consent,
)


def test_new_consent_defaults_to_keep_and_confirmed():
    c = new_consent("Burt")
    assert c.volunteer_label == "Burt"
    assert c.retention_policy == "keep"
    assert c.confirmed_by_operator is True
    assert c.confirmed_at  # ISO timestamp present


def test_new_consent_rejects_bad_retention():
    with pytest.raises(ValueError):
        new_consent("Burt", "forever")


def test_require_consent_passes_valid():
    c = new_consent("Burt", "ephemeral")
    assert require_consent(c) is c


def test_require_consent_none_raises():
    with pytest.raises(ConsentNotProvided):
        require_consent(None)


def test_require_consent_unconfirmed_raises():
    c = ConsentRecord(
        volunteer_label="Burt",
        confirmed_at="2026-06-06T00:00:00+00:00",
        confirmed_by_operator=False,
        retention_policy="keep",
    )
    with pytest.raises(ConsentNotProvided):
        require_consent(c)


def test_require_consent_invalid_policy_raises():
    c = ConsentRecord(
        volunteer_label="Burt",
        confirmed_at="2026-06-06T00:00:00+00:00",
        confirmed_by_operator=True,
        retention_policy="whenever",
    )
    with pytest.raises(ConsentNotProvided):
        require_consent(c)


def test_consent_round_trips_through_dict():
    c = new_consent("Élodie", "delete_after_show")
    restored = ConsentRecord.from_dict(c.to_dict())
    assert restored == c
