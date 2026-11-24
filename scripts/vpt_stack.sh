#!/usr/bin/env bash
# Stack reale per lavorare sul simulatore senza mock: Postgres 16 con le
# migrazioni di produzione e il runner Prosimos 2.1 (Python 3.12).
# Pensato per le sessioni cloud senza Docker; gira anche su Linux in locale.
#
#   scripts/vpt_stack.sh start    # avvia tutto e stampa le variabili da esportare
#   scripts/vpt_stack.sh status   # cosa gira
#   scripts/vpt_stack.sh stop     # spegne tutto
#   eval "$(scripts/vpt_stack.sh env)"   # variabili nella shell corrente
#
# Le password sono quelle di test della CI: lo stack è solo locale (127.0.0.1).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STATE="${VPT_STACK_DIR:-/var/tmp/delir-vpt-stack}"
PG_BIN="/usr/lib/postgresql/16/bin"
PG_DATA="$STATE/pg"
PG_PORT="${VPT_PG_PORT:-5432}"
RUNNER_PORT="${VPT_RUNNER_PORT:-5000}"
RUNNER_VENV="$STATE/runner-venv"
RUNNER_PID="$STATE/runner.pid"
RUNNER_LOG="$STATE/runner.log"

export POSTGRES_USER=delir_super POSTGRES_DB=delir
export DELIR_MIGRATOR_PASSWORD=ci-migrator DELIR_APP_PASSWORD=ci-app
export DELIR_WORKER_PASSWORD=ci-worker DELIR_MEM0_PASSWORD=ci-mem0
export DELIR_WORKSPACE_PASSWORD=ci-workspace

env_lines() {
  cat <<EOF
export WORKSPACE_DATABASE_URL=postgresql+psycopg://delir_workspace:ci-workspace@127.0.0.1:$PG_PORT/workspace
export CANONICAL_DATABASE_URL=postgresql+psycopg://delir_app:ci-app@127.0.0.1:$PG_PORT/delir
export CANONICAL_MIGRATOR_URL=postgresql+psycopg://delir_migrator:ci-migrator@127.0.0.1:$PG_PORT/delir
export CANONICAL_WORKER_URL=postgresql+psycopg://delir_worker:ci-worker@127.0.0.1:$PG_PORT/delir
export PROSIMOS_BASE_URL=http://127.0.0.1:$RUNNER_PORT
EOF
}

# I processi in background non tengono stdout/stderr del chiamante: altrimenti
# `scripts/vpt_stack.sh start | tail` non finirebbe mai.
# Postgres non parte come root: i comandi del cluster girano come utente postgres.
as_pg() {
  if [ "$(id -u)" = 0 ]; then runuser -u postgres -- "$@"; else "$@"; fi
}

pg_running() { as_pg "$PG_BIN/pg_ctl" -D "$PG_DATA" status >/dev/null 2>&1; }
runner_running() { [ -f "$RUNNER_PID" ] && kill -0 "$(cat "$RUNNER_PID")" 2>/dev/null; }

install_packages() {
  local missing=()
  [ -x "$PG_BIN/initdb" ] || missing+=(postgresql-16)
  [ -f /usr/share/postgresql/16/extension/vector.control ] || missing+=(postgresql-16-pgvector)
  if [ ${#missing[@]} -gt 0 ]; then
    echo "installo ${missing[*]}"
    apt-get install -y -qq "${missing[@]}" >/dev/null 2>&1 \
      || { apt-get update -qq >/dev/null && apt-get install -y -qq "${missing[@]}" >/dev/null; }
  fi
}

start_postgres() {
  mkdir -p "$STATE"
  [ "$(id -u)" = 0 ] && chown postgres "$STATE"
  if [ ! -f "$PG_DATA/PG_VERSION" ]; then
    echo "creo il cluster Postgres in $PG_DATA"
    as_pg "$PG_BIN/initdb" -D "$PG_DATA" -U "$POSTGRES_USER" --auth=trust -E UTF8 >/dev/null
    local fresh=1
  fi
  if ! pg_running; then
    as_pg "$PG_BIN/pg_ctl" -D "$PG_DATA" -l "$STATE/pg.log" -w \
      -o "-p $PG_PORT -c listen_addresses=127.0.0.1 -k $STATE" start </dev/null >/dev/null 2>&1
  fi
  if [ "${fresh:-0}" = 1 ]; then
    as_pg psql -h 127.0.0.1 -p "$PG_PORT" -U "$POSTGRES_USER" -d postgres -q -c "CREATE DATABASE delir"
    for script in "$ROOT"/ops/postgres/init/*.sh; do
      PGHOST=127.0.0.1 PGPORT="$PG_PORT" bash "$script" >/dev/null
    done
  fi
  echo "migrazioni (canonical + workspace)"
  (cd "$ROOT" && eval "$(env_lines)" \
    && uv run -q alembic upgrade head >/dev/null \
    && uv run -q alembic -c alembic_workspace.ini upgrade head >/dev/null)
}

start_runner() {
  if [ ! -x "$RUNNER_VENV/bin/gunicorn" ]; then
    echo "creo il venv del runner (Python 3.12, Prosimos 2.1)"
    uv venv -q --python 3.12 "$RUNNER_VENV"
    uv pip install -q --python "$RUNNER_VENV/bin/python" -r "$ROOT/ops/prosimos/runner/requirements-test.txt"
  fi
  if ! runner_running; then
    (cd "$ROOT/ops/prosimos/runner" && RUNNER_DATA_DIR="$STATE/runner-data" \
      nohup "$RUNNER_VENV/bin/gunicorn" --bind "127.0.0.1:$RUNNER_PORT" \
        --workers "${GUNICORN_WORKERS:-4}" --timeout "${GUNICORN_TIMEOUT:-1800}" \
        runner:app </dev/null >"$RUNNER_LOG" 2>&1 & echo $! >"$RUNNER_PID")
  fi
  for _ in $(seq 1 60); do
    curl -fsS "http://127.0.0.1:$RUNNER_PORT/health" >/dev/null 2>&1 && return 0
    sleep 1
  done
  echo "il runner non risponde: vedi $RUNNER_LOG" >&2
  return 1
}

status() {
  if pg_running; then echo "postgres: attivo su 127.0.0.1:$PG_PORT"; else echo "postgres: spento"; fi
  if runner_running && health=$(curl -fsS "http://127.0.0.1:$RUNNER_PORT/health" 2>/dev/null); then
    echo "runner:   attivo su 127.0.0.1:$RUNNER_PORT $health"
  else
    echo "runner:   spento"
  fi
}

case "${1:-}" in
  start)
    install_packages
    start_postgres
    start_runner
    status
    echo
    echo "# esporta nella shell con: eval \"\$(scripts/vpt_stack.sh env)\""
    env_lines
    ;;
  env) env_lines ;;
  status) status ;;
  stop)
    if runner_running; then kill "$(cat "$RUNNER_PID")"; rm -f "$RUNNER_PID"; fi
    if pg_running; then as_pg "$PG_BIN/pg_ctl" -D "$PG_DATA" -m fast stop >/dev/null; fi
    status
    ;;
  *)
    sed -n '2,11p' "$0" | sed 's/^# \{0,1\}//'
    exit 2
    ;;
esac
