"""The Heavy decision trace — one ordered, self-explaining record per flight.

Every wrong Heavy verdict before this cost a screenshot-and-guess cycle: the
report showed a Yes or a No and nothing about how it got there. A trace step
names the rule that ran, what it decided, and the exact inputs it decided on —
airports in every form received, times as received, the operating counts, and
the two crew sets actually compared.

Pure and dependency-free by design: ``heavy`` and ``unknown_resolver`` both
build steps, and neither may grow an import of the service layer to do it.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Any, Mapping, Sequence


@dataclass(frozen=True)
class HeavyTraceStep:
    """One evaluated rule: what it was, what it concluded, what it saw."""

    step: str
    outcome: str
    inputs: Mapping[str, Any]


def step(name: str, outcome: str, **inputs: Any) -> HeavyTraceStep:
    """Build a step, keeping the inputs JSON-shaped for the API payload."""

    return HeavyTraceStep(step=name, outcome=outcome, inputs=dict(inputs))


def as_received(values: Sequence[str | None] | None) -> list[str]:
    """The values exactly as they arrived, minus the ones that never arrived.

    No trimming, no upper-casing: a trace that normalizes its inputs cannot
    show that the two sides disagreed about the form of a code.
    """

    if not values:
        return []
    return [value for value in values if isinstance(value, str)]


def format_break(duration: timedelta) -> str:
    """Render a break as H:MM, the form the rotation rule is discussed in."""

    total_minutes = int(duration.total_seconds() // 60)
    sign = "-" if total_minutes < 0 else ""
    total_minutes = abs(total_minutes)
    return f"{sign}{total_minutes // 60}:{total_minutes % 60:02d}"
