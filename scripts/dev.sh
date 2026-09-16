#!/usr/bin/env bash
# One-command local development bootstrap.
#
#   ./scripts/dev.sh setup   install dependencies, migrate, seed
#   ./scripts/dev.sh api     run the API on :8000
#   ./scripts/dev.sh web     run the UI on :5173
#   ./scripts/dev.sh test    run backend + frontend tests
#   ./scripts/dev.sh check   lint, typecheck, tests, build — the CI gate locally
#   ./scripts/dev.sh reset   drop the local database and reseed

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
API="$ROOT/apps/api"
WEB="$ROOT/apps/web"
VENV="$API/.venv"

info() { printf '\033[1;34m==>\033[0m %s\n' "$*"; }
fail() { printf '\033[1;31mERROR:\033[0m %s\n' "$*" >&2; exit 1; }

python_bin() {
  if [ -x "$VENV/bin/python" ]; then echo "$VENV/bin/python"; else echo "python3"; fi
}

require() { command -v "$1" >/dev/null 2>&1 || fail "$1 is required but was not found on PATH."; }

setup() {
  require python3
  require node

  info "Creating the Python virtual environment"
  [ -d "$VENV" ] || python3 -m venv "$VENV"
  "$VENV/bin/pip" install --quiet --upgrade pip
  info "Installing API dependencies"
  (cd "$API" && "$VENV/bin/pip" install --quiet -e ".[dev]")

  info "Installing web dependencies"
  (cd "$WEB" && npm install --no-audit --no-fund)

  [ -f "$ROOT/.env" ] || { cp "$ROOT/.env.example" "$ROOT/.env"; info "Created .env from .env.example"; }

  info "Running migrations"
  (cd "$API" && "$VENV/bin/alembic" upgrade head)

  info "Seeding demo data"
  (cd "$API" && "$VENV/bin/python" -m app.db.seed)

  cat <<'EOS'

Setup complete.

  Terminal 1:  ./scripts/dev.sh api
  Terminal 2:  ./scripts/dev.sh web

  UI    http://localhost:5173
  API   http://localhost:8000/docs
  Login admin@contoso.com / Passw0rd!Demo
EOS
}

case "${1:-help}" in
  setup) setup ;;
  api)   (cd "$API" && "$(python_bin)" -m uvicorn app.main:app --reload --port 8000) ;;
  web)   (cd "$WEB" && npm run dev) ;;
  worker) (cd "$API" && "$(python_bin)" -m app.worker) ;;
  seed)  (cd "$API" && "$(python_bin)" -m app.db.seed) ;;
  reset)
    info "Dropping the local database and reseeding"
    (cd "$API" && "$(python_bin)" -m app.db.seed --reset)
    ;;
  test)
    info "Backend tests"
    (cd "$API" && "$(python_bin)" -m pytest -q)
    info "Frontend tests"
    (cd "$WEB" && npm test)
    ;;
  check)
    info "Backend lint"
    (cd "$API" && "$(python_bin)" -m ruff check .)
    info "Backend tests"
    (cd "$API" && "$(python_bin)" -m pytest -q)
    info "Frontend lint"
    (cd "$WEB" && npm run lint)
    info "Frontend typecheck"
    (cd "$WEB" && npm run typecheck)
    info "Frontend tests"
    (cd "$WEB" && npm test)
    info "Frontend build"
    (cd "$WEB" && npm run build)
    info "All checks passed."
    ;;
  *)
    sed -n '2,10p' "$0" | sed 's/^# \{0,1\}//'
    ;;
esac
