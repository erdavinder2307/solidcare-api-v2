# Solidcare API V2

FastAPI-based modular monolith backend for the Solidcare healthcare platform.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate   # On Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env with your settings

# Run migrations
alembic upgrade head

# Seed demo admin user (optional, for local dev)
docker exec -i solidcare_db psql -U solidcare -d solidcare_dev < scripts/seed_dev_admin.sql

# Seed RBAC role users for local dev / E2E (see scripts/seed_dev_rbac_users.sql)
docker exec -i solidcare_db psql -U solidcare -d solidcare_dev < scripts/seed_dev_rbac_users.sql

# Start the server
uvicorn app.main:app --reload
```

## Project Structure

```
app/
├── main.py              # FastAPI app factory
├── config.py            # Settings (pydantic-settings)
├── database.py          # Async SQLAlchemy engine
├── core/
│   ├── security/        # JWT, password hashing, TOTP MFA
│   ├── exceptions/      # Custom errors + global handlers
│   ├── middleware/       # Tenant context, audit, rate limiting
│   ├── events/          # In-process event bus
│   └── background/      # Celery app + tasks
├── modules/             # Domain modules (auth, patients, doctors, ...)
└── shared/              # Base models, pagination, utilities
```

## Available Endpoints

| Module | Base Path |
|---|---|
| Authentication | `/api/v1/auth` |
| Patients | `/api/v1/patients` |
| Doctors | `/api/v1/doctors` |
| Appointments | `/api/v1/appointments` |
| Encounters | `/api/v1/encounters` |
| Prescriptions | `/api/v1/prescriptions` |
| Billing (Invoices) | `/api/v1/billing/invoices` |
| Billing (Payments) | `/api/v1/billing/payments` |
| Notifications | `/api/v1/notifications` |
| Reports | `/api/v1/reports` |
| Audit Logs | `/api/v1/audit` |

## Database Migrations

```bash
# Create a new migration
alembic revision --autogenerate -m "description of change"

# Apply migrations
alembic upgrade head

# Rollback one step
alembic downgrade -1
```

## Running Tests

```bash
pytest tests/ -v --tb=short
```

## Running Celery Worker

```bash
celery -A app.core.background.celery_app worker --loglevel=info
celery -A app.core.background.celery_app beat --loglevel=info
```
