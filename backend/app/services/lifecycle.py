"""The opportunity status state machine.

Status is not a free-text label. An opportunity that has been scored cannot go
back to merely discovered, and nothing comes back out of ``ARCHIVED``. Encoding
the legal moves in one place means an illegal transition fails loudly at the
point of the mistake rather than producing a row that later queries quietly
misinterpret.

Every accepted transition yields an event to append to ``opportunity_events``,
which is what makes "what changed since I last looked" answerable.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any

from app.core.errors import ValidationError
from app.models.enums import OpportunityEventType, OpportunityStatus

S = OpportunityStatus

#: Terminal states an opportunity can always fall into: it can be superseded,
#: rejected or shelved from anywhere it has not already ended up.
_EXITS: frozenset[OpportunityStatus] = frozenset({S.ARCHIVED, S.EXPIRED, S.REJECTED, S.DUPLICATE})

#: Forward progress through enrichment. Each stage adds information the next
#: one depends on.
_PIPELINE: Mapping[OpportunityStatus, frozenset[OpportunityStatus]] = MappingProxyType(
    {
        # Stages may be skipped: Phase 2 scores a freshly ingested row without
        # an enrichment pass, and a later agent may still walk the long way.
        S.DISCOVERED: frozenset({S.ENRICHED, S.QUALIFIED, S.SCORED, S.RECOMMENDED}),
        S.ENRICHED: frozenset({S.QUALIFIED, S.SCORED, S.RECOMMENDED}),
        S.QUALIFIED: frozenset({S.SCORED, S.RECOMMENDED}),
        S.SCORED: frozenset({S.RECOMMENDED, S.QUALIFIED}),
        # A recommendation can be recomputed, which lands back on SCORED.
        S.RECOMMENDED: frozenset({S.SCORED}),
        S.EXPIRED: frozenset(),
        S.REJECTED: frozenset(),
        S.DUPLICATE: frozenset(),
        S.ARCHIVED: frozenset(),
    }
)

#: Statuses from which nothing further may happen.
TERMINAL: frozenset[OpportunityStatus] = frozenset({S.ARCHIVED})

#: Statuses excluded from ranking and recommendation.
INACTIVE: frozenset[OpportunityStatus] = frozenset({S.ARCHIVED, S.EXPIRED, S.REJECTED, S.DUPLICATE})

#: The event a transition into each status records. Anything not named here is
#: logged as a generic status change.
_ENTRY_EVENTS: Mapping[OpportunityStatus, OpportunityEventType] = MappingProxyType(
    {
        S.ENRICHED: OpportunityEventType.ENRICHED,
        S.SCORED: OpportunityEventType.SCORED,
        S.RECOMMENDED: OpportunityEventType.RECOMMENDED,
        S.EXPIRED: OpportunityEventType.EXPIRED,
        S.DUPLICATE: OpportunityEventType.DEDUPLICATED,
        S.REJECTED: OpportunityEventType.DISMISSED,
    }
)


@dataclass(frozen=True, slots=True)
class LifecycleEvent:
    """A transition that happened, ready to be persisted."""

    event_type: OpportunityEventType
    payload: dict[str, Any] = field(default_factory=dict)


def allowed_transitions(current: OpportunityStatus) -> frozenset[OpportunityStatus]:
    """Every status reachable from ``current`` in one step."""
    if current in TERMINAL:
        return frozenset()
    return _PIPELINE[current] | (_EXITS - {current})


def can_transition(current: OpportunityStatus, target: OpportunityStatus) -> bool:
    return target in allowed_transitions(current)


def transition(
    current: OpportunityStatus,
    target: OpportunityStatus,
    *,
    reason: str | None = None,
    **payload: Any,
) -> LifecycleEvent | None:
    """Validate a status change and describe the event it produces.

    Returns ``None`` when the status is unchanged, so callers can apply a desired
    state idempotently without generating a stream of no-op events.
    """
    if current == target:
        return None
    if not can_transition(current, target):
        raise ValidationError(f"cannot move an opportunity from {current.value} to {target.value}")

    body: dict[str, Any] = {"from": current.value, "to": target.value, **payload}
    if reason:
        body["reason"] = reason
    return LifecycleEvent(
        event_type=_ENTRY_EVENTS.get(target, OpportunityEventType.STATUS_CHANGED),
        payload=body,
    )
