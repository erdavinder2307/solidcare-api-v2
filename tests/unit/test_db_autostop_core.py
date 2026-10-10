"""Idle and wake decisions of the database auto-stop function (infra/db-autostop)."""

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "infra" / "db-autostop"))

from autostop_core import (  # noqa: E402
    REASON_IDLE,
    REASON_IDLE_AFTER_OUTSIDE_START,
    WakeReply,
    decide_stop,
    metric_filter,
    metric_values,
    next_ready_since,
    wake_reply,
)

NOW = datetime(2026, 10, 10, 12, 0, tzinfo=timezone.utc)
LONG_AGO = NOW - timedelta(hours=2)


def test_stops_after_30_idle_minutes():
    decision = decide_stop("Ready", LONG_AGO, [0.0] * 30, NOW, started_by_wake=True)
    assert decision.stop
    assert decision.reason == REASON_IDLE


def test_one_transaction_keeps_it_running():
    values = [0.0] * 29 + [3.0]
    assert not decide_stop("Ready", LONG_AGO, values, NOW, started_by_wake=True).stop


def test_too_few_metric_points_keeps_it_running():
    # e.g. the metrics setting is off or the metric pipeline lags: never stop on missing data
    assert not decide_stop("Ready", LONG_AGO, [0.0] * 19, NOW, started_by_wake=True).stop


def test_recently_started_server_gets_a_full_window():
    ready_since = NOW - timedelta(minutes=29)
    assert not decide_stop("Ready", ready_since, [0.0] * 30, NOW, started_by_wake=True).stop
    assert not decide_stop("Ready", None, [0.0] * 30, NOW, started_by_wake=True).stop


def test_only_ready_servers_are_stopped():
    for state in ("Stopped", "Starting", "Stopping", "Updating"):
        assert not decide_stop(state, LONG_AGO, [0.0] * 30, NOW, started_by_wake=True).stop


def test_seven_day_auto_start_is_stopped_again_with_its_reason():
    decision = decide_stop("Ready", LONG_AGO, [0.0] * 30, NOW, started_by_wake=False)
    assert decision.stop
    assert decision.reason == REASON_IDLE_AFTER_OUTSIDE_START


def test_ready_since_starts_on_first_ready_sighting_and_then_holds():
    assert next_ready_since("Ready", "Stopped", None, NOW) == NOW
    assert next_ready_since("Ready", None, None, NOW) == NOW  # first run ever
    assert next_ready_since("Ready", "Ready", LONG_AGO, NOW) == LONG_AGO
    assert next_ready_since("Stopped", "Ready", LONG_AGO, NOW) is None


def test_metric_values_skips_points_without_a_total():
    timeseries = [
        {
            "data": [
                {"timeStamp": "a", "total": 0.0},
                {"timeStamp": "b"},
                {"timeStamp": "c", "total": 2},
            ]
        },
        {"data": [{"timeStamp": "a", "total": 1.0}]},
    ]
    assert metric_values(timeseries) == [0.0, 2.0, 1.0]
    assert metric_values([]) == []


def test_metric_filter_limits_to_app_databases():
    assert metric_filter(["solidcare"]) == "DatabaseName eq 'solidcare'"
    assert metric_filter(["a", "b"]) == "DatabaseName eq 'a' or DatabaseName eq 'b'"


def test_wake_is_idempotent_per_state():
    assert wake_reply("Stopped") == WakeReply(True, 202, "starting")
    assert wake_reply("Starting") == WakeReply(False, 202, "starting")
    assert wake_reply("Updating") == WakeReply(False, 202, "starting")
    assert wake_reply("Ready") == WakeReply(False, 200, "ready")
    assert wake_reply("Stopping") == WakeReply(False, 202, "stopping")
    assert wake_reply("Disabled") == WakeReply(False, 503, "unavailable")
