#!/usr/bin/env bash
# Backup di DeliR: i tre database Postgres e i file caricati, cifrati e fuori dalla VM.
#
# Cosa entra in un backup (un file `delir-<UTC>.tar.age`):
#   - `delir`, `workspace`, `mem0`: pg_dump in formato custom. Neo4j no: e' una
#     proiezione di `delir` e si ricostruisce (scripts/kg_reproject.py);
#   - `appdata.tar.gz`: i documenti e gli audio caricati dai consulenti;
#   - `manifest.json`: per ogni database le righe di ogni tabella, contate nella
#     **stessa fotografia** del dump (snapshot esportato), e lo sha256 di ogni file.
#     La prova di ripristino (restore.sh --check) confronta con queste.
#
# Cifratura con age verso una chiave PUBBLICA: la VM sa cifrare ma non
# decifrare. La chiave privata sta fuori dalla VM (runbook: ops/backup/README.md).
#
# Variabili:
#   PGHOST PGPORT PGUSER PGPASSWORD  il superuser del cluster (legge tutto, RLS compresa)
#   BACKUP_AGE_RECIPIENT             obbligatoria: chiave pubblica age (age1...)
#   BACKUP_REMOTE                    obbligatoria: destinazione rclone (oci:bucket/delir) o una cartella
#   BACKUP_DATABASES                 default "delir workspace mem0"
#   BACKUP_APPDATA_DIR               default /appdata; se non esiste si salta, e lo si dice
#   BACKUP_RETENTION_DAYS            default 30: i backup piu' vecchi si cancellano dalla destinazione
#   BACKUP_WORK_DIR                  default /tmp/delir-backup
#   BACKUP_STATUS_FILE               se impostata, ci scrive l'esito (JSON) per il controllo di salute
set -euo pipefail

: "${BACKUP_AGE_RECIPIENT:?serve BACKUP_AGE_RECIPIENT (chiave pubblica age)}"
: "${BACKUP_REMOTE:?serve BACKUP_REMOTE (destinazione rclone)}"
DATABASES="${BACKUP_DATABASES:-delir workspace mem0}"
APPDATA_DIR="${BACKUP_APPDATA_DIR:-/appdata}"
RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-30}"
WORK_ROOT="${BACKUP_WORK_DIR:-/tmp/delir-backup}"

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
NAME="delir-${STAMP}"
WORK="${WORK_ROOT}/${NAME}"
STARTED=$(date +%s)

log() { echo "[backup ${STAMP}] $*" >&2; }

status() {
  # $1 ok|failed, $2 messaggio
  [ -n "${BACKUP_STATUS_FILE:-}" ] || return 0
  printf '{"status": "%s", "backup": "%s", "at": "%s", "seconds": %s, "message": %s}\n' \
    "$1" "$NAME" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$(( $(date +%s) - STARTED ))" \
    "$(printf '%s' "$2" | python3 -c 'import json,sys; print(json.dumps(sys.stdin.read()))' 2>/dev/null || echo '""')" \
    > "${BACKUP_STATUS_FILE}.tmp" && mv "${BACKUP_STATUS_FILE}.tmp" "${BACKUP_STATUS_FILE}"
}

cleanup() { rm -rf "$WORK" "${WORK_ROOT:?}/${NAME}.tar" "${WORK_ROOT:?}/${NAME}.tar.age"; }
fail() { log "FALLITO: $*"; status failed "$*"; cleanup; exit 1; }
trap 'fail "errore alla riga $LINENO"' ERR

mkdir -p "$WORK"

# Conta le righe di ogni tabella e fa il dump nella stessa fotografia: una
# transazione REPEATABLE READ resta aperta (coprocesso psql), esporta lo
# snapshot, e pg_dump lo usa. Le scritture che arrivano nel frattempo non
# entrano ne' nel conteggio ne' nel dump.
dump_database() {
  local db="$1"
  local counts="$WORK/${db}.counts"
  coproc PSQL { psql -X -qAt -v ON_ERROR_STOP=1 -d "$db"; }
  echo "BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY; SELECT pg_export_snapshot();" >&"${PSQL[1]}"
  local snapshot
  read -r snapshot <&"${PSQL[0]}"
  cat >&"${PSQL[1]}" <<'SQL'
SELECT coalesce(string_agg(format('SELECT %L, count(*) FROM %I.%I', schemaname || '.' || relname, schemaname, relname), ' UNION ALL ' ORDER BY schemaname, relname), 'SELECT NULL, NULL WHERE false')
FROM pg_stat_user_tables \gexec
SELECT '__FINE__';
SQL
  : > "$counts"
  local line
  while read -r line <&"${PSQL[0]}"; do
    [ "$line" = "__FINE__" ] && break
    echo "$line" >> "$counts"
  done
  pg_dump --snapshot="$snapshot" -Fc -d "$db" -f "$WORK/${db}.dump"
  echo "COMMIT;" >&"${PSQL[1]}"
  exec {PSQL[1]}>&-
  wait "$PSQL_PID" 2>/dev/null || true
  log "$db: $(wc -l < "$counts") tabelle, $(du -h "$WORK/${db}.dump" | cut -f1)"
}

for db in $DATABASES; do
  dump_database "$db"
done

if [ -d "$APPDATA_DIR" ]; then
  tar -C "$APPDATA_DIR" -czf "$WORK/appdata.tar.gz" .
  log "file caricati: $(du -h "$WORK/appdata.tar.gz" | cut -f1)"
else
  log "ATTENZIONE: $APPDATA_DIR non esiste, i file caricati non sono nel backup"
fi

# Il manifesto: righe per tabella e sha256 di ogni file.
python3 - "$WORK" "$STAMP" "$DATABASES" <<'PY'
import hashlib, json, pathlib, sys
work, stamp, dbs = pathlib.Path(sys.argv[1]), sys.argv[2], sys.argv[3].split()
manifest = {"format": 1, "created_at": stamp, "databases": {}, "files": {}}
for db in dbs:
    rows = {}
    for line in (work / f"{db}.counts").read_text().splitlines():
        if "|" in line:
            table, count = line.rsplit("|", 1)
            rows[table] = int(count)
    manifest["databases"][db] = {"dump": f"{db}.dump", "rows": rows}
    (work / f"{db}.counts").unlink()
for path in sorted(work.iterdir()):
    manifest["files"][path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
(work / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
PY

tar -C "$WORK_ROOT" -cf "${WORK_ROOT}/${NAME}.tar" "$NAME"
age -r "$BACKUP_AGE_RECIPIENT" -o "${WORK_ROOT}/${NAME}.tar.age" "${WORK_ROOT}/${NAME}.tar"
rm -f "${WORK_ROOT}/${NAME}.tar"

rclone copyto --no-traverse "${WORK_ROOT}/${NAME}.tar.age" "${BACKUP_REMOTE%/}/${NAME}.tar.age"
SIZE=$(du -h "${WORK_ROOT}/${NAME}.tar.age" | cut -f1)
log "caricato in ${BACKUP_REMOTE%/}/${NAME}.tar.age ($SIZE)"

# Conservazione: i backup piu' vecchi di RETENTION_DAYS escono dalla destinazione.
rclone delete --min-age "${RETENTION_DAYS}d" --include "delir-*.tar.age" "${BACKUP_REMOTE%/}" || \
  log "ATTENZIONE: pulizia dei backup vecchi non riuscita"

cleanup
trap - ERR
status ok "$NAME ($SIZE)"
log "fatto in $(( $(date +%s) - STARTED )) s"
echo "$NAME.tar.age"
