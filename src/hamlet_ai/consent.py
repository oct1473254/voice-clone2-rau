"""Consent records and gating for voice cloning.

Cloning a volunteer's voice is the single most sensitive thing this app does, so
no clone may proceed without an explicit :class:`ConsentRecord`. The record is
written into the RunFolder's ``clone_metadata.json`` and (from Step 4) onto the
``VoiceEntry`` so there is a durable audit trail of who consented and to what
retention policy.

Importing this module has no side effects.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone


VALID_RETENTION_POLICIES = {"keep", "ephemeral", "delete_after_show"}


class ConsentNotProvided(Exception):
    """Raised by the pipeline when a clone is attempted without valid consent."""


@dataclass(frozen=True)
class ConsentRecord:
    volunteer_label: str
    confirmed_at: str  # ISO 8601 UTC
    confirmed_by_operator: bool
    retention_policy: str  # one of VALID_RETENTION_POLICIES

    def to_dict(self) -> dict:
        return {
            "volunteer_label": self.volunteer_label,
            "confirmed_at": self.confirmed_at,
            "confirmed_by_operator": self.confirmed_by_operator,
            "retention_policy": self.retention_policy,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ConsentRecord":
        return cls(
            volunteer_label=data["volunteer_label"],
            confirmed_at=data["confirmed_at"],
            confirmed_by_operator=bool(data["confirmed_by_operator"]),
            retention_policy=data["retention_policy"],
        )


def new_consent(
    volunteer_label: str,
    retention_policy: str = "keep",
    *,
    confirmed: bool = True,
    now: datetime | None = None,
) -> ConsentRecord:
    """Build a :class:`ConsentRecord`, validating the retention policy."""
    if retention_policy not in VALID_RETENTION_POLICIES:
        raise ValueError(
            f"invalid retention_policy {retention_policy!r}; "
            f"expected one of {sorted(VALID_RETENTION_POLICIES)}"
        )
    ts = (now or datetime.now(timezone.utc)).isoformat(timespec="seconds")
    return ConsentRecord(
        volunteer_label=volunteer_label or "volunteer",
        confirmed_at=ts,
        confirmed_by_operator=confirmed,
        retention_policy=retention_policy,
    )


def require_consent(consent: ConsentRecord | None) -> ConsentRecord:
    """Return ``consent`` if it is valid, else raise :class:`ConsentNotProvided`."""
    if consent is None:
        raise ConsentNotProvided(
            "Voice cloning requires explicit consent. No ConsentRecord was provided."
        )
    if not consent.confirmed_by_operator:
        raise ConsentNotProvided(
            "Voice cloning requires the operator to confirm volunteer consent."
        )
    if consent.retention_policy not in VALID_RETENTION_POLICIES:
        raise ConsentNotProvided(
            f"ConsentRecord has invalid retention_policy {consent.retention_policy!r}."
        )
    return consent
