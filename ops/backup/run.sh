#!/usr/bin/env bash
# Il servizio di backup: un backup al giorno all'ora indicata, e il controllo di salute.
#
#   run.sh schedule   ogni giorno alle BACKUP_AT (UTC, default 02:30); con
#                     BACKUP_ON_START=true anche subito, per provare la configurazione
#   run.sh now        un backup adesso, ed esce
#   run.sh restore …  restore.sh con i suoi argomenti (runbook: ripristino)
#   run.sh health     0 se l'ultimo backup e' riuscito da meno di BACKUP_MAX_AGE_HOURS
#                     (default 26); e' il HEALTHCHECK del container
#
# Un backup fallito non ferma il servizio: lo dice il controllo di salute (il
# container diventa `unhealthy`) e il log, e la notte dopo si riprova.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export BACKUP_STATUS_FILE="${BACKUP_STATUS_FILE:-/status/last-backup.json}"
mkdir -p "$(dirname "$BACKUP_STATUS_FILE")"

seconds_until() {
  # secondi fino alla prossima HH:MM UTC
  python3 - "$1" <<'PY'
import datetime as dt, sys
hh, mm = (int(x) for x in sys.argv[1].split(":"))
now = dt.datetime.now(dt.UTC)
nxt = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
if nxt <= now:
    nxt += dt.timedelta(days=1)
print(int((nxt - now).total_seconds()))
PY
}

health() {
  python3 - "$BACKUP_STATUS_FILE" "${BACKUP_MAX_AGE_HOURS:-26}" <<'PY'
import datetime as dt, json, sys
try:
    status = json.load(open(sys.argv[1]))
except (OSError, ValueError):
    sys.exit("nessun backup ancora registrato")
if status.get("status") != "ok":
    sys.exit(f"ultimo backup fallito: {status.get('message')}")
at = dt.datetime.fromisoformat(status["at"].replace("Z", "+00:00"))
age = (dt.datetime.now(dt.UTC) - at).total_seconds() / 3600
if age > float(sys.argv[2]):
    sys.exit(f"ultimo backup riuscito {age:.0f} ore fa")
print(f"ok: {status['backup']}, {age:.1f} ore fa")
PY
}

case "${1:-schedule}" in
  now) exec "$HERE/backup.sh" ;;
  restore) shift; exec "$HERE/restore.sh" "$@" ;;
  health) health ;;
  schedule)
    # All'avvio solo se non c'e' gia' un backup riuscito recente: un riavvio o un
    # deploy non devono rifare un dump intero mentre le persone lavorano.
    if [ "${BACKUP_ON_START:-false}" = true ] && ! BACKUP_MAX_AGE_HOURS=20 health >/dev/null 2>&1; then
      "$HERE/backup.sh" || echo "[backup] fallito all'avvio: vedi sopra" >&2
    fi
    while true; do
      wait_s=$(seconds_until "${BACKUP_AT:-02:30}")
      echo "[backup] prossimo backup fra $(( wait_s / 3600 )) h $(( wait_s % 3600 / 60 )) min" >&2
      sleep "$wait_s"
      "$HERE/backup.sh" || echo "[backup] fallito: vedi sopra, si riprova domani" >&2
    done
    ;;
  *) echo "uso: run.sh schedule|now|health" >&2; exit 2 ;;
esac
