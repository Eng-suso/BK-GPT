#!/bin/bash
# Bootstrap dei ruoli — gira UNA VOLTA come superuser, al primo init del volume.
# Crea i tre ruoli applicativi (nessuno superuser / BYPASSRLS / owner), assegna
# lo schema public a delir_migrator, abilita le estensioni.
#
# Le migration Alembic girano poi come delir_migrator e fanno il resto.
set -euo pipefail

psql -v ON_ERROR_STOP=1 \
  -v migrator_pw="${DELIR_MIGRATOR_PASSWORD}" \
  -v app_pw="${DELIR_APP_PASSWORD}" \
  -v worker_pw="${DELIR_WORKER_PASSWORD}" \
  --username "${POSTGRES_USER}" --dbname "${POSTGRES_DB}" <<'SQL'
CREATE ROLE delir_migrator LOGIN PASSWORD :'migrator_pw'
  NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS;
CREATE ROLE delir_app LOGIN PASSWORD :'app_pw'
  NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS;
CREATE ROLE delir_worker LOGIN PASSWORD :'worker_pw'
  NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS;

-- delir_migrator possiede lo schema di lavoro
ALTER SCHEMA public OWNER TO delir_migrator;
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
GRANT USAGE ON SCHEMA public TO delir_app, delir_worker;

-- estensioni (servono privilegi da superuser)
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
SQL

echo "bootstrap ruoli DeliR completato"
