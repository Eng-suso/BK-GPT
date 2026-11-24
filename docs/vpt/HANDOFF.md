# Dove siamo adesso

Aggiornato: 2026-11-24, chiusura di CAL-01.

## Punto attivo

Nessuno. **CAL-01 è fatto** (`feat/sim-fuzzy-calendars`, PR sopra #170): gli scenari
SIMOD con calendari FUZZY si importano, si ricompilano identici e girano su Prosimos 2.1.
Si mergia dopo #170 (B1a + B1b).

Prossimo: **UX-01** (leggibilità di "Reale contro simulato") oppure **B2** (harness di
valutazione), come da `PLAN.md`.

## Ultima misura

CAL-01: scenario scoperto da SIMOD 5.2.1 sul log del dataset
(`datasets/simod/discovered/Insurance_Claims_fuzzy/`, `config.yml` accanto): round trip
identico e 100 casi sul motore; disponibilità al 20% contro 95% → tempo di ciclo medio
~193.000 s contro ~1.800 s. Suite `tests/simulation` con Postgres: 675 passati.

## Da sapere sui calendari FUZZY

- Prosimos considera libera una risorsa se lo dice la disponibilità **o** il carico
  (`FuzzyModel.is_available`): un carico a 1 annulla la disponibilità.
- La granularità deve dividere la giornata in fasce uguali di minuti interi.
- Ogni fascia vuole la sua probabilità: Prosimos non ha un default e si ferma.
- Per rilanciare SIMOD: venv Python 3.12, `pip install` del repo SIMOD dalla cache
  (`scripts/fetch_datasets.py fetch simod`), serve Java; un errore Java finale sul
  layout del BPMN non impedisce `best_result/`.

## CI

Fino al 2026-11-23 `main` era rosso su 5 e2e del simulatore (`simulation-escalation`,
`simulation-eventlog`), rimasti indietro rispetto ai commit del 23 novembre. La PR
#168 li ha corretti: un difetto vero (log con soli completamenti senza confronto per
attività) e test con copy e mock vecchi.

## Ambiente

- Sessioni cloud sull'ambiente **BK-GPT** (consente zenodo.org e data.4tu.nl).
- I test che non toccano il database girano con `uv run pytest --noconftest ...`;
  la suite completa richiede Postgres (`cd ops && docker compose up -d`) o la CI.
- Postgres in cloud senza Docker (il daemon non c'è): `apt-get install -y
  postgresql-16-pgvector`, poi come utente `postgres` `initdb -U delir_super
  --auth=trust` in `/var/lib/postgresql/delir-test/data`, `pg_ctl ... -o '-p 5432
  -c listen_addresses=127.0.0.1' start`, `CREATE DATABASE delir`, gli script
  `ops/postgres/init/*.sh` con `POSTGRES_USER=delir_super POSTGRES_DB=delir` e le
  password di test della CI, poi `alembic upgrade head` e
  `alembic -c alembic_workspace.ini upgrade head` con le URL della CI. Con questo la
  suite `tests/simulation` gira intera (655 test il 2026-11-23).
- Playwright in cloud: il repo fissa una versione diversa da quella preinstallata.
  Usa una config locale non committata che estende `playwright.config.ts` con
  `launchOptions.executablePath: '/opt/pw-browsers/chromium'`.

## Decisioni aperte per Sohayb

- Copiare comunque nel repo pubblico BPIC 2012/2013/2020 e Prosimos?
- Confermare le mete marcate *proposta* in `PLAN.md` (B2: scarto ≤ 10% dal paper;
  B3: gateway ±0,05, durate ±10%).
