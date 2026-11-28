# Backup e ripristino di DeliR

Ogni notte la produzione salva i tre database Postgres e i file caricati dai
consulenti, li cifra e li porta su OCI Object Storage, fuori dalla VM. Il
ripristino è provato da uno script, non presunto.

| | |
|---|---|
| **Cosa si salva** | `delir` (memoria, grafo canonico), `workspace` (clienti, progetti, chat, consumi), `mem0`; i file caricati (volume `delir_appdata`) |
| **Cosa no, e perché** | Neo4j: è una proiezione di `delir` e si ricostruisce (`scripts/kg_reproject.py`). Le identità delle persone stanno in Supabase. |
| **Quando** | Ogni giorno alle `BACKUP_AT` (UTC, default 02:30), e all'avvio del servizio |
| **Quanto si può perdere (RPO)** | Al massimo 24 ore di lavoro |
| **Quanto si impiega a ripartire (RTO)** | Misurato il 2026-11-28: 13 s per ripristinare 300.000 righe su un cluster nuovo. Con la VM da rifare servono anche il provisioning e il pull delle immagini, quindi va dichiarata un'ora. |
| **Conservazione** | 30 giorni (`BACKUP_RETENTION_DAYS`) |
| **Cifratura** | age, verso una chiave **pubblica**: la VM cifra e non sa decifrare |

## Preparazione (una volta, da Sohayb)

1. **La chiave**, sul tuo computer e non sulla VM:
   ```bash
   age-keygen -o delir-backup-key.txt     # stampa la chiave pubblica: age1...
   ```
   Conserva `delir-backup-key.txt` in un password manager e in una seconda copia
   offline. **Senza questo file nessun backup si può aprire, nemmeno da noi.**
2. **Il bucket** in OCI Object Storage:
   - privato;
   - nella stessa regione della VM, o in un'altra per sopravvivere alla regione;
   - con una lifecycle rule che cancella oltre 35 giorni, come rete di sicurezza
     della conservazione dello script.
3. **La chiave di accesso:** una *Customer Secret Key* dell'utente OCI che scrive
   nel bucket (API compatibile S3). Dagli il permesso di scrivere solo in quel
   bucket.
4. **Nel `.env` della VM** (vedi `ops/.env.example`):
   ```bash
   BACKUP_AGE_RECIPIENT=age1...                 # la chiave PUBBLICA
   BACKUP_REMOTE=oci:delir-backup/prod          # <bucket>/<cartella>
   OCI_S3_ENDPOINT=https://<namespace>.compat.objectstorage.<regione>.oraclecloud.com
   OCI_S3_REGION=<regione>                      # es. eu-frankfurt-1
   OCI_S3_ACCESS_KEY=...
   OCI_S3_SECRET_KEY=...
   ```

## Avvio e controllo

```bash
cd ops
docker compose -f docker-compose.yml -f docker-compose.prod.yml -f docker-compose.backup.yml up -d
docker logs -f delir-backup          # il primo backup parte subito
docker inspect --format '{{.State.Health.Status}}' delir-backup
```

Il container diventa `unhealthy` se l'ultimo backup riuscito ha più di 26 ore,
o se l'ultimo è fallito. Un backup a mano:
`docker exec delir-backup /backup/run.sh now`.

## Prova di ripristino (ogni trimestre, e dopo ogni cambio di questo setup)

Sul tuo computer, con la chiave privata. Non tocca niente di vivo: ripristina in
database temporanei `<db>_restore_check`, confronta le righe di ogni tabella
con il manifesto del backup (contate nella stessa fotografia del dump), poi li
cancella, anche se la prova fallisce. Serve un Postgres 16 con i ruoli di DeliR:
quello della VM attraverso Tailscale, o uno locale inizializzato con
`ops/postgres/init/` (per esempio lo stack di sviluppo, `cd ops && docker
compose up -d postgres`). Un Postgres qualsiasi non basta: il dump assegna
tabelle e regole ai ruoli `delir_*`.

```bash
export PGHOST=... PGPORT=5432 PGUSER=delir_super PGPASSWORD=...
export BACKUP_AGE_IDENTITY=~/delir-backup-key.txt
export BACKUP_REMOTE=oci:delir-backup/prod RCLONE_CONFIG_OCI_TYPE=s3 ...   # come sopra
ops/backup/restore.sh --check latest
```

Deve finire con `PROVA RIUSCITA` e, per ogni database, `tutte uguali`. Annota
data ed esito qui sotto.

| Data | Backup | Esito | Durata |
|---|---|---|---|
| 2026-11-28 | locale (sviluppo) | 3 database, 295.883 righe, tutte uguali; file caricati leggibili | 13 s |

## Disastro: ripristinare la produzione

1. VM nuova (o la stessa con il volume perso): stack dei dati su con
   `docker compose ... up -d postgres neo4j docling`. L'init del volume crea
   ruoli e database vuoti.
2. **App ferma.** Ripristino:
   ```bash
   cd ops
   docker compose -f docker-compose.yml -f docker-compose.prod.yml -f docker-compose.backup.yml \
     run --rm --no-deps \
     -v ~/delir-backup-key.txt:/key.txt:ro -e BACKUP_AGE_IDENTITY=/key.txt \
     -v delir_appdata:/restore-appdata -e BACKUP_APPDATA_DIR=/restore-appdata \
     backup restore --live --yes latest
   ```
   Il servizio monta i file caricati in sola lettura su `/appdata`: per
   riscriverli si monta lo stesso volume, scrivibile, su `/restore-appdata`.
   Lo script verifica l'integrità del file (sha256 del manifesto), sovrascrive i
   database, confronta le righe con il manifesto e rimette i file caricati.
3. Avvio dell'app. Le migrazioni sono già a head: il dump le contiene.
4. Ricostruire il grafo: `python -m scripts.kg_reproject --client <uuid> --apply`
   per ogni cliente.
5. Togliere la chiave privata dalla VM.

Provato il 2026-11-28 su un cluster Postgres 16 nuovo, inizializzato con
`ops/postgres/init/`:
- righe uguali al manifesto in tutte le 62 tabelle;
- migrazioni a head;
- RLS attiva: `delir_app` vede 0 righe senza contesto e quelle del consulente
  con il contesto.

## Dove sta il codice

- `backup.sh`, `restore.sh`, `run.sh` (pianificazione e controllo di salute),
  `Dockerfile`.
- `ops/docker-compose.backup.yml`: il servizio, solo in produzione.
- `tests/server/test_backup_restore.py`: backup e prova di ripristino sul
  Postgres dei test, archivio manomesso rifiutato, `--live` senza `--yes`
  rifiutato. Gira in CI.
