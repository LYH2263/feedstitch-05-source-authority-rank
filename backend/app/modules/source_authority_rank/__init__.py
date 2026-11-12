"""Cross-source authority order for same-key divergent records.

The authority rank is a per-source integer: a larger number is more
authoritative.  It is stored on ``sources.authority_rank`` and can be edited
from the source management page.

Rules for a same-business-key record whose non-key fields diverge from the
canonical row:

* incoming rank strictly higher than the current owner -> ``authority_override``
  (write canonical and keep an auditable authority-change record)
* incoming rank strictly lower than the current owner -> ``authority_lost``
  (never touch canonical; quarantine with the authority-loss reason)
* equal ranks or an unknown/missing owner rank -> ``conflict`` (quarantine;
  never silently overwrite)

This module is deliberately pure: the ingest service supplies the ranks and
persists the resulting decision.
"""

from __future__ import annotations

HIGHER = "higher"
LOWER = "lower"
EQUAL = "equal"
UNKNOWN = "unknown"

DECISION_OVERRIDE = "authority_override"
DECISION_LOST = "authority_lost"
DECISION_CONFLICT = "conflict"

REASON_LOST = "authority_lost"
REASON_EQUAL = "authority_equal"
REASON_UNKNOWN = "authority_unknown"
REASON_MISMATCH = "non_key_field_mismatch"


def compare_authority(incoming_rank: int | None, owner_rank: int | None) -> str:
    """Compare two authority ranks without deciding anything.

    ``None`` means the rank could not be determined (for example the canonical
    owner source no longer exists).
    """

    if incoming_rank is None or owner_rank is None:
        return UNKNOWN
    if incoming_rank > owner_rank:
        return HIGHER
    if incoming_rank < owner_rank:
        return LOWER
    return EQUAL


def decide_divergence(incoming_rank: int | None, owner_rank: int | None) -> str:
    """Decide what to do when non-key fields diverge for the same key."""

    comparison = compare_authority(incoming_rank, owner_rank)
    if comparison == HIGHER:
        return DECISION_OVERRIDE
    if comparison == LOWER:
        return DECISION_LOST
    # equal / unknown -> stay in conflict quarantine
    return DECISION_CONFLICT


def conflict_reason(
    incoming_rank: int | None,
    owner_rank: int | None,
    decision: str = DECISION_CONFLICT,
) -> str:
    """Human- and audit-readable reason stored on the conflict row."""

    if decision == DECISION_LOST:
        return REASON_LOST
    comparison = compare_authority(incoming_rank, owner_rank)
    if comparison == UNKNOWN:
        return REASON_UNKNOWN
    if comparison == EQUAL:
        return REASON_EQUAL
    return REASON_MISMATCH
