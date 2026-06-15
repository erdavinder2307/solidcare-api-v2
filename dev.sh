#!/usr/bin/env bash
# ============================================================
# Solidcare API v2 – local development startup script
# Run from: solidcare-api-v2/
# ============================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$SCRIPT_DIR"

VENV_DIR=".venv"
ENV_FILE=".env"

# ── Colours ──────────────────────────────────────────────────
GREEN="\033[0;32m"; YELLOW="\033[1;33m"; RED="\033[0;31m"; NC="\033[0m"
info()    { echo -e "${GREEN}[API]${NC} $*"; }
warn()    { echo -e "${YELLOW}[API]${NC} $*"; }
error()   { echo -e "${RED}[API]${NC} $*"; exit 1; }

# ── Check Python ─────────────────────────────────────────────
if ! command -v python3 &>/dev/null; then
  error "python3 not found. Please install Python 3.11+."
fi

# ── Check Docker ──────────────────────────────────────────────
if ! command -v docker &>/dev/null; then
  error "docker not found. Please install Docker Desktop."
fi

# ── Virtual environment ───────────────────────────────────────
if [ ! -d "$VENV_DIR" ]; then
  info "Creating virtual environment at $VENV_DIR …"
  python3 -m venv "$VENV_DIR"
fi

info "Activating virtual environment …"
# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"

# ── Install / sync dependencies ───────────────────────────────
info "Installing/syncing Python dependencies …"
pip install --quiet --upgrade pip
pip install --quiet -r requirements.txt

# ── Environment file ──────────────────────────────────────────
if [ ! -f "$ENV_FILE" ]; then
  if [ -f ".env.example" ]; then
    warn ".env not found — copying from .env.example"
    cp .env.example "$ENV_FILE"
  else
    warn ".env not found and no .env.example available. Continuing with defaults."
  fi
fi

# ── Start infrastructure (Postgres + Redis) via Docker Compose ─
info "Starting infrastructure services (db, redis) …"
docker compose -f "$ROOT_DIR/docker-compose.yml" up -d db redis

# ── Wait for Postgres to be healthy ──────────────────────────
info "Waiting for PostgreSQL to be ready …"
MAX_WAIT=60
ELAPSED=0
until docker compose -f "$ROOT_DIR/docker-compose.yml" exec -T db \
    pg_isready -U solidcare -d solidcare_dev -q 2>/dev/null; do
  if [ "$ELAPSED" -ge "$MAX_WAIT" ]; then
    error "PostgreSQL did not become ready within ${MAX_WAIT}s. Check 'docker compose logs db'."
  fi
  sleep 2
  ELAPSED=$(( ELAPSED + 2 ))
done
info "PostgreSQL is ready ✓"

# ── Wait for Redis to be healthy ──────────────────────────────
info "Waiting for Redis to be ready …"
ELAPSED=0
until docker compose -f "$ROOT_DIR/docker-compose.yml" exec -T redis \
    redis-cli ping 2>/dev/null | grep -q PONG; do
  if [ "$ELAPSED" -ge "$MAX_WAIT" ]; then
    error "Redis did not become ready within ${MAX_WAIT}s. Check 'docker compose logs redis'."
  fi
  sleep 2
  ELAPSED=$(( ELAPSED + 2 ))
done
info "Redis is ready ✓"

# ── Run Alembic migrations ────────────────────────────────────
info "Running Alembic database migrations …"
alembic upgrade head

# ── Start Uvicorn ─────────────────────────────────────────────
HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8000}"
RELOAD="${RELOAD:-true}"

info "Starting FastAPI server on http://${HOST}:${PORT} (reload=${RELOAD}) …"
info "API docs → http://localhost:${PORT}/docs"

exec uvicorn app.main:app \
  --host "$HOST" \
  --port "$PORT" \
  $( [ "$RELOAD" = "true" ] && echo "--reload" ) \
  --log-level info
