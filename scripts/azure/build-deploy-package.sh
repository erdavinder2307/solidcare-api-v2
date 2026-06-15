#!/usr/bin/env bash
# Build an offline App Service deployment package (no Oryx build on server).
# Usage: bash scripts/azure/build-deploy-package.sh [output_dir]

set -euo pipefail

API_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
OUT="${1:-/tmp/solidcare-api-deploy}"

echo "Building API package at $OUT"
rm -rf "$OUT"
mkdir -p "$OUT/.python_packages/lib/site-packages"

cp -R \
  "$API_ROOT/app" \
  "$API_ROOT/migrations" \
  "$API_ROOT/alembic.ini" \
  "$API_ROOT/application.py" \
  "$API_ROOT/startup.sh" \
  "$API_ROOT/.deployment" \
  "$OUT/"

# Runtime-only dependencies — omit pytest/factory-boy/faker from the deploy zip.
grep -vE '^(pytest|factory-boy|faker)' "$API_ROOT/requirements.txt" > "$OUT/requirements.txt"

chmod +x "$OUT/startup.sh"

cd "$OUT"
python3 -m pip install -r requirements.txt -t .python_packages/lib/site-packages \
  --platform manylinux2014_x86_64 --python-version 3.11 --only-binary=:all: \
  2>/dev/null \
  || python3 -m pip install -r requirements.txt -t .python_packages/lib/site-packages

find . -type d -name __pycache__ -prune -exec rm -rf {} + 2>/dev/null || true
find . -type f -name '*.pyc' -delete 2>/dev/null || true

echo "Package ready: $OUT"
