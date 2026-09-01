#!/bin/bash
# Database isolato per la projection Mem0 OSS (D1).
# Gira come superuser al primo init del volume, dopo 00-bootstrap.sh.
#
# Mem0 crea da solo la sua tabella collection (pgvector) nel db `mem0`; qui
# creiamo solo il ruolo, il database che possiede, e le estensioni (che
# richiedono privilegi da superuser e sono per-database).
set -euo pipefail

psql -v ON_ERROR_STOP=1 \
  -v mem0_pw="${DELIR_MEM0_PASSWORD}" \
  --username "${POSTGRES_USER}" --dbname "${POSTGRES_DB}" <<'SQL'
CREATE ROLE delir_mem0 LOGIN PASSWORD :'mem0_pw'
  NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS;
SQL

psql -v ON_ERROR_STOP=1 --username "${POSTGRES_USER}" --dbname "${POSTGRES_DB}" \
  -c "CREATE DATABASE mem0 OWNER delir_mem0;"

psql -v ON_ERROR_STOP=1 --username "${POSTGRES_USER}" --dbname mem0 <<'SQL'
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
SQL

echo "database mem0 pronto"
