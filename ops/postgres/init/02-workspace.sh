#!/bin/bash
# Database dello stato operativo locale: workspace (clienti/progetti/processi/
# BPMN/simulazioni), cronologia chat, indice della memoria episodica.
#
# Isolato dal canonical (schema public) e da mem0: churn operativo alto, niente
# RLS, ruolo proprio. Gira come superuser al primo init del volume.
#
# `delir_workspace` possiede il database e ci fa DDL: l'app crea le tabelle con
# SQLAlchemy `metadata.create_all` alla prima connessione.
set -euo pipefail

psql -v ON_ERROR_STOP=1 \
  -v ws_pw="${DELIR_WORKSPACE_PASSWORD}" \
  --username "${POSTGRES_USER}" --dbname "${POSTGRES_DB}" <<'SQL'
CREATE ROLE delir_workspace LOGIN PASSWORD :'ws_pw'
  NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS;
SQL

psql -v ON_ERROR_STOP=1 --username "${POSTGRES_USER}" --dbname "${POSTGRES_DB}" \
  -c "CREATE DATABASE workspace OWNER delir_workspace;"

echo "database workspace pronto"
