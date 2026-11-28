#!/usr/bin/env bash
# Ripristino di un backup di DeliR (fatto da backup.sh). Due modi:
#
#   restore.sh --check  [<file>|latest]   prova: ripristina in database temporanei
#                                          (<db>_restore_check), confronta le righe di
#                                          ogni tabella con il manifesto, poi li cancella.
#                                          Non tocca niente di vivo. Da fare ogni trimestre.
#   restore.sh --live --yes [<file>|latest]
#                                          disastro: sovrascrive i database veri e i file
#                                          caricati. L'app va fermata prima.
#
# Il file si prende da BACKUP_REMOTE (latest = il piu' recente), o e' un percorso locale.
#
# Variabili:
#   PGHOST PGPORT PGUSER PGPASSWORD  il superuser del cluster di destinazione
#   BACKUP_AGE_IDENTITY              obbligatoria: file della chiave PRIVATA age (fuori dalla VM)
#   BACKUP_REMOTE                    da dove scaricare (per un nome o per latest)
#   BACKUP_APPDATA_DIR               default /appdata: dove tornano i file caricati (--live)
#   BACKUP_WORK_DIR                  default /tmp/delir-restore
set -euo pipefail

MODE=""
CONFIRMED=""
SOURCE="latest"
for arg in "$@"; do
  case "$arg" in
    --check) MODE=check ;;
    --live) MODE=live ;;
    --yes) CONFIRMED=yes ;;
    -*) echo "opzione sconosciuta: $arg" >&2; exit 2 ;;
    *) SOURCE="$arg" ;;
  esac
done
[ -n "$MODE" ] || { echo "uso: restore.sh --check|--live --yes [<file>|latest]" >&2; exit 2; }
if [ "$MODE" = live ] && [ "$CONFIRMED" != yes ]; then
  echo "--live sovrascrive i database veri: aggiungi --yes, a app ferma." >&2
  exit 2
fi
: "${BACKUP_AGE_IDENTITY:?serve BACKUP_AGE_IDENTITY (file della chiave privata age)}"
APPDATA_DIR="${BACKUP_APPDATA_DIR:-/appdata}"
WORK_ROOT="${BACKUP_WORK_DIR:-/tmp/delir-restore}"
STARTED=$(date +%s)

log() { echo "[restore] $*" >&2; }
mkdir -p "$WORK_ROOT"
WORK="$(mktemp -d "${WORK_ROOT}/run-XXXXXX")"
trap 'rm -rf "$WORK"' EXIT

# 1. Il file cifrato.
if [ -f "$SOURCE" ]; then
  ARCHIVE="$SOURCE"
else
  : "${BACKUP_REMOTE:?serve BACKUP_REMOTE per scaricare il backup}"
  if [ "$SOURCE" = latest ]; then
    SOURCE="$(rclone lsf --include 'delir-*.tar.age' "${BACKUP_REMOTE%/}" | sort | tail -1)"
    [ -n "$SOURCE" ] || { log "nessun backup in ${BACKUP_REMOTE}"; exit 1; }
  fi
  rclone copyto "${BACKUP_REMOTE%/}/$(basename "$SOURCE")" "$WORK/$(basename "$SOURCE")"
  ARCHIVE="$WORK/$(basename "$SOURCE")"
fi
log "backup: $(basename "$ARCHIVE")"

# 2. Decifrare, aprire, verificare gli sha256 del manifesto.
age -d -i "$BACKUP_AGE_IDENTITY" -o "$WORK/backup.tar" "$ARCHIVE"
tar -C "$WORK" -xf "$WORK/backup.tar"
rm -f "$WORK/backup.tar"
DIR="$(find "$WORK" -mindepth 1 -maxdepth 1 -type d -name 'delir-*' | head -1)"
[ -f "$DIR/manifest.json" ] || { log "manifest.json assente: non e' un backup di backup.sh"; exit 1; }
python3 - "$DIR" <<'PY'
import hashlib, json, pathlib, sys
d = pathlib.Path(sys.argv[1])
manifest = json.loads((d / "manifest.json").read_text())
for name, digest in manifest["files"].items():
    if hashlib.sha256((d / name).read_bytes()).hexdigest() != digest:
        sys.exit(f"sha256 diverso per {name}: il backup e' corrotto")
PY
log "integrita' verificata"

DATABASES="$(python3 -c 'import json,sys; print(" ".join(json.load(open(sys.argv[1]))["databases"]))' "$DIR/manifest.json")"

# Le righe di ogni tabella del database ripristinato, nello stesso formato del manifesto.
count_rows() {
  psql -X -qAt -v ON_ERROR_STOP=1 -d "$1" <<'SQL'
SELECT coalesce(string_agg(format('SELECT %L, count(*) FROM %I.%I', schemaname || '.' || relname, schemaname, relname), ' UNION ALL ' ORDER BY schemaname, relname), 'SELECT NULL, NULL WHERE false')
FROM pg_stat_user_tables \gexec
SQL
}

compare_rows() {
  # $1 database del manifesto, $2 database ripristinato
  count_rows "$2" > "$WORK/$1.restored"
  python3 - "$DIR/manifest.json" "$1" "$WORK/$1.restored" <<'PY'
import json, sys
expected = json.load(open(sys.argv[1]))["databases"][sys.argv[2]]["rows"]
got = {}
for line in open(sys.argv[3]).read().splitlines():
    if "|" in line:
        table, count = line.rsplit("|", 1)
        got[table] = int(count)
diff = {t: (expected.get(t), got.get(t)) for t in set(expected) | set(got) if expected.get(t) != got.get(t)}
if diff:
    for table, (want, have) in sorted(diff.items()):
        print(f"  {table}: atteso {want}, ripristinato {have}", file=sys.stderr)
    sys.exit(f"{sys.argv[2]}: {len(diff)} tabelle diverse dal manifesto")
print(f"{sys.argv[2]}: {len(expected)} tabelle, {sum(expected.values())} righe, tutte uguali", file=sys.stderr)
PY
}

if [ "$MODE" = check ]; then
  for db in $DATABASES; do
    target="${db}_restore_check"
    psql -X -q -v ON_ERROR_STOP=1 -d postgres -c "DROP DATABASE IF EXISTS \"$target\" WITH (FORCE)" -c "CREATE DATABASE \"$target\""
    pg_restore --exit-on-error -d "$target" "$DIR/$db.dump"
    compare_rows "$db" "$target"
    psql -X -q -v ON_ERROR_STOP=1 -d postgres -c "DROP DATABASE \"$target\" WITH (FORCE)"
  done
  if [ -f "$DIR/appdata.tar.gz" ]; then
    tar -tzf "$DIR/appdata.tar.gz" > /dev/null
    log "file caricati: archivio leggibile ($(tar -tzf "$DIR/appdata.tar.gz" | grep -vc '/$') file)"
  fi
  log "PROVA RIUSCITA in $(( $(date +%s) - STARTED )) s: il backup si ripristina ed e' completo"
  exit 0
fi

# --live: i database esistono gia' (li crea l'init del cluster, con i loro ruoli).
for db in $DATABASES; do
  log "ripristino $db"
  pg_restore --clean --if-exists --exit-on-error -d "$db" "$DIR/$db.dump"
  compare_rows "$db" "$db"
done
if [ -f "$DIR/appdata.tar.gz" ]; then
  mkdir -p "$APPDATA_DIR"
  tar -C "$APPDATA_DIR" -xzf "$DIR/appdata.tar.gz"
  log "file caricati ripristinati in $APPDATA_DIR"
fi
log "RIPRISTINO COMPLETATO in $(( $(date +%s) - STARTED )) s. Poi: avviare l'app (migrazioni a head),"
log "e ricostruire il grafo Neo4j: python -m scripts.kg_reproject --apply"
