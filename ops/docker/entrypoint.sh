#!/bin/sh
# Avvio del container di DeliR: prima lo schema, poi l'app.
#
# Le migrazioni girano qui e non nell'app (RUN_MIGRATIONS_ON_STARTUP=false
# nell'immagine): un solo migratore alla volta, sotto lock di Postgres
# (scripts/migrate.py). Se falliscono il container esce e l'app non parte su
# uno schema a meta'.
#
# Un solo worker uvicorn, di proposito: i lock dei turni di chat stanno in
# memoria di processo (fragilita-status.md, B4). Due worker corromperebbero i
# checkpoint di una conversazione.
set -eu

python -m scripts.migrate

exec uvicorn backend.app:app \
  --host 0.0.0.0 \
  --port "${PORT:-8000}" \
  --workers 1 \
  --proxy-headers \
  --forwarded-allow-ips "${FORWARDED_ALLOW_IPS:-127.0.0.1}"
