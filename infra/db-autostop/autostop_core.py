"""Decisions for the SolidCare dev database auto-stop function. No Azure imports, so the
API's unit tests can cover them.

Idle rule: the server has been Ready for at least IDLE_MINUTES and the `xact_total` metric
(transactions, filtered to the app databases) is 0 in every one-minute point of the last
IDLE_MINUTES, with at least MIN_POINTS points reported. Active connections are not used: the
API's connection pool keeps idle connections open.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

IDLE_MINUTES = 30
MIN_POINTS = 20

READY = "Ready"
STOPPED = "Stopped"
STARTING_STATES = {"Starting", "Updating"}

REASON_IDLE = "idle"
REASON_IDLE_AFTER_OUTSIDE_START = (
    "idle after a start outside wake (7-day auto-start, maintenance or manual)"
)


@dataclass(frozen=True)
class StopDecision:
    stop: bool
    reason: str


@dataclass(frozen=True)
class WakeReply:
    start: bool  # call the start API
    http_status: int
    state: str  # "ready" | "starting" | "stopping" | "unavailable"


def metric_values(timeseries: list[dict]) -> list[float]:
    """The `total` of every one-minute point that has one, across all returned series."""
    values: list[float] = []
    for series in timeseries:
        for point in series.get("data", []):
            if point.get("total") is not None:
                values.append(float(point["total"]))
    return values


def decide_stop(
    state: str,
    ready_since: datetime | None,
    xact_values: list[float],
    now: datetime,
    started_by_wake: bool,
) -> StopDecision:
    """Whether the timer should stop the server now, and why."""
    if state != READY:
        return StopDecision(False, f"state {state}")
    if ready_since is None or now - ready_since < timedelta(minutes=IDLE_MINUTES):
        return StopDecision(False, "up for less than the idle window")
    if len(xact_values) < MIN_POINTS:
        return StopDecision(False, f"only {len(xact_values)} metric points (need {MIN_POINTS})")
    if any(value > 0 for value in xact_values):
        return StopDecision(False, "active")
    return StopDecision(True, REASON_IDLE if started_by_wake else REASON_IDLE_AFTER_OUTSIDE_START)


def next_ready_since(
    state: str, previous_state: str | None, previous_ready_since: datetime | None, now: datetime
) -> datetime | None:
    """Track when the server became Ready. The first sighting of a Ready server whose start
    we did not see counts from now, so it always gets a full idle window."""
    if state != READY:
        return None
    if previous_state == READY and previous_ready_since is not None:
        return previous_ready_since
    return now


def wake_reply(state: str) -> WakeReply:
    """What the wake route does for the server's current state. Idempotent."""
    if state == READY:
        return WakeReply(False, 200, "ready")
    if state == STOPPED:
        return WakeReply(True, 202, "starting")
    if state in STARTING_STATES:
        return WakeReply(False, 202, "starting")
    if state == "Stopping":
        # Start is only allowed from Stopped; the caller retries with backoff.
        return WakeReply(False, 202, "stopping")
    return WakeReply(False, 503, "unavailable")


def metric_filter(database_names: list[str]) -> str:
    """Azure Monitor $filter limiting xact_total to the app databases (system databases such
    as azure_maintenance have their own activity)."""
    return " or ".join(f"DatabaseName eq '{name}'" for name in database_names)
