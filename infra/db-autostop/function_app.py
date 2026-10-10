"""SolidCare dev database auto-stop: stop the PostgreSQL Flexible Server when idle, start it
on demand. Runs with a managed identity whose custom role can only read metrics and read,
start and stop this one server (deploy.sh).

App settings: SUBSCRIPTION_ID, RESOURCE_GROUP, SERVER_NAME, DATABASE_NAMES (comma separated),
AzureWebJobsStorage (state and event log tables).
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta, timezone

import azure.functions as func
import requests
from autostop_core import (
    IDLE_MINUTES,
    READY,
    decide_stop,
    metric_filter,
    metric_values,
    next_ready_since,
    wake_reply,
)
from azure.core.exceptions import ResourceNotFoundError
from azure.data.tables import TableServiceClient
from azure.identity import ManagedIdentityCredential

app = func.FunctionApp()

ARM = "https://management.azure.com"
SERVER_API = "2024-08-01"
METRICS_API = "2023-10-01"
STATE_TABLE = "dbautostopstate"
EVENT_TABLE = "dbautostopevents"
STATE_KEY = ("server", "state")

_credential = ManagedIdentityCredential()


def _server_id() -> str:
    return (
        f"/subscriptions/{os.environ['SUBSCRIPTION_ID']}/resourceGroups/{os.environ['RESOURCE_GROUP']}"
        f"/providers/Microsoft.DBforPostgreSQL/flexibleServers/{os.environ['SERVER_NAME']}"
    )


def _headers() -> dict[str, str]:
    token = _credential.get_token(f"{ARM}/.default").token
    return {"Authorization": f"Bearer {token}"}


def _server_state() -> str:
    r = requests.get(
        f"{ARM}{_server_id()}", params={"api-version": SERVER_API}, headers=_headers(), timeout=30
    )
    r.raise_for_status()
    return r.json()["properties"]["state"]


def _server_action(action: str) -> None:
    r = requests.post(
        f"{ARM}{_server_id()}/{action}",
        params={"api-version": SERVER_API},
        headers=_headers(),
        timeout=30,
    )
    r.raise_for_status()  # 202 Accepted: the operation continues in Azure


def _xact_values(now: datetime) -> list[float]:
    start = now - timedelta(minutes=IDLE_MINUTES)
    names = [n.strip() for n in os.environ["DATABASE_NAMES"].split(",") if n.strip()]
    params = {
        "api-version": METRICS_API,
        "metricnames": "xact_total",
        "timespan": f"{start:%Y-%m-%dT%H:%M:%SZ}/{now:%Y-%m-%dT%H:%M:%SZ}",
        "interval": "PT1M",
        "aggregation": "Total",
        "$filter": metric_filter(names),
    }
    r = requests.get(
        f"{ARM}{_server_id()}/providers/Microsoft.Insights/metrics",
        params=params,
        headers=_headers(),
        timeout=30,
    )
    r.raise_for_status()
    metrics = r.json().get("value", [])
    return metric_values(metrics[0].get("timeseries", [])) if metrics else []


def _tables():
    service = TableServiceClient.from_connection_string(os.environ["AzureWebJobsStorage"])
    state = service.create_table_if_not_exists(STATE_TABLE)
    events = service.create_table_if_not_exists(EVENT_TABLE)
    return state, events


def _load_state(table) -> dict:
    try:
        return dict(table.get_entity(*STATE_KEY))
    except ResourceNotFoundError:
        return {}


def _save_state(table, **fields) -> None:
    table.upsert_entity({"PartitionKey": STATE_KEY[0], "RowKey": STATE_KEY[1], **fields})


def _log_event(table, now: datetime, event: str, reason: str) -> None:
    """One row per stop/start, kept to report the hours saved."""
    table.create_entity(
        {
            "PartitionKey": f"{now:%Y-%m}",
            "RowKey": f"{now:%Y%m%dT%H%M%S%f}",
            "event": event,
            "reason": reason,
        }
    )
    logging.info("db-autostop %s: %s", event, reason)


def _parse(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


@app.timer_trigger(schedule="0 */10 * * * *", arg_name="timer", run_on_startup=False)
def idle_check(timer: func.TimerRequest) -> None:
    now = datetime.now(timezone.utc)
    state_table, events = _tables()
    saved = _load_state(state_table)
    state = _server_state()

    ready_since = next_ready_since(
        state, saved.get("last_state"), _parse(saved.get("ready_since")), now
    )
    start_source = saved.get("start_source") or ""
    if state == READY and saved.get("last_state") != READY:
        if start_source != "wake":
            start_source = "outside"
        _log_event(
            events,
            now,
            "started",
            "wake"
            if start_source == "wake"
            else "outside wake (7-day auto-start, maintenance or manual)",
        )

    decision = decide_stop(
        state, ready_since, _xact_values(now) if state == READY else [], now, start_source == "wake"
    )
    if decision.stop:
        _server_action("stop")
        _log_event(events, now, "stopped", decision.reason)
        state, ready_since, start_source = "Stopping", None, ""

    _save_state(
        state_table,
        last_state=state,
        ready_since=ready_since.isoformat() if ready_since else "",
        start_source=start_source,
        checked_at=now.isoformat(),
    )


@app.route(route="wake", methods=["POST"], auth_level=func.AuthLevel.FUNCTION)
def wake(req: func.HttpRequest) -> func.HttpResponse:
    reply = wake_reply(_server_state())
    if reply.start:
        now = datetime.now(timezone.utc)
        state_table, events = _tables()
        _server_action("start")
        saved = _load_state(state_table)
        saved.update(start_source="wake", wake_at=now.isoformat())
        _save_state(
            state_table, **{k: v for k, v in saved.items() if k not in ("PartitionKey", "RowKey")}
        )
        _log_event(events, now, "start requested", "wake")
    return func.HttpResponse(
        json.dumps({"state": reply.state}),
        status_code=reply.http_status,
        mimetype="application/json",
    )
