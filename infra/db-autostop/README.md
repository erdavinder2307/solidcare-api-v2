# Database auto-stop (dev)

The dev database only holds test data and is idle most of the day. This Azure Function stops the
PostgreSQL Flexible Server when nobody has used it for 30 minutes and starts it again on demand, so its
compute is billed only while someone is working. Storage is still billed while it is stopped.

## How it works

- **Idle check (timer, every 10 minutes).** Reads the server's `xact_total` metric (transactions per
  minute) for the watched databases (`DATABASE_NAMES`). If the server has been Ready for 30+ minutes and
  every one-minute point of the last 30 minutes is 0 (at least 20 points present), it stops the server.
  Active connections are not used: the API's connection pool keeps idle connections open.
- **Wake (`POST /api/wake`, function key).** Starts the server if it is stopped and returns
  `{"state": ...}`: 200 when ready, 202 while starting or stopping. Calling it again is safe.
- **The API.** When `DB_WAKE_URL` and `DB_WAKE_KEY` are set and the database cannot be reached, a
  request calls wake (at most once per backoff step: now, then 1, 2, 4, 5 minutes) and gets a 503 with
  `error_code: DB_STARTING` and `Retry-After: 30` instead of a 500.
  `GET`/`POST /health/db` answers `{"database": "ready"}` or a 503 `{"database": "starting"}` and wakes
  the server. Login screens call it once when they open and poll it while they show the waiting state.
  With auto-stop on, `/health` does not open a connection (the App Service health check calls it every
  minute, which would keep the database awake).
- **Log.** Each stop and start is a row in the `dbautostopevents` table (partition = month) with its
  reason: `idle`, `wake`, or `outside wake` (Azure's 7-day auto-start, a maintenance start, or a manual
  start). A start outside wake gets a full 30-minute window before it can be stopped again.

Azure rules this relies on: a stopped server starts by itself after 7 days, a stop only works from Ready
and a start only from Stopped
([stop](https://learn.microsoft.com/en-us/azure/postgresql/configure-maintain/how-to-stop-server),
[start](https://learn.microsoft.com/en-us/azure/postgresql/configure-maintain/how-to-start-server)).
`xact_total` is an enhanced metric that needs the server parameter
`metrics.collector_database_activity=on` (dynamic, no restart;
[monitoring](https://learn.microsoft.com/en-us/azure/postgresql/monitor/concepts-monitoring)).
A start usually takes 2–5 minutes.

## Permissions

The function uses its system-assigned managed identity with a custom role that is assignable only on
the one server: read the server, start it, stop it, read its metrics. No keys are stored in code.

## Commands

Set `RESOURCE_GROUP`, `SERVER_NAME`, `DATABASE_NAMES`, `API_APP`, `FUNC_APP`, `STORAGE_ACCOUNT` and
`LOCATION`, then:

```bash
infra/db-autostop/deploy.sh plan     # dry run: what deploy would create, and the role scope
infra/db-autostop/deploy.sh deploy   # create/update and publish
infra/db-autostop/deploy.sh status   # state of the server, function, role and settings
infra/db-autostop/deploy.sh wake     # start the database now (same path the API uses)
infra/db-autostop/deploy.sh stop     # stop it now
```

## Turning it off

`infra/db-autostop/deploy.sh off` stops the function app (kept, not deleted), removes `DB_WAKE_URL` and
`DB_WAKE_KEY` from the API (the API then behaves exactly as before) and starts the server, so it stays on.
Run `deploy` again to turn auto-stop back on.

## Tests

```bash
pytest tests/unit/test_db_autostop_core.py tests/unit/test_db_wake.py tests/unit/test_db_health_route.py
```
