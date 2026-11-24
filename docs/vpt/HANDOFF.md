# Dove siamo adesso

Aggiornato: 2026-11-24, dopo CONF-01, CONF-02 (conformance log ↔ BPMN), SEC-ADMIN,
B1a e B1b (import Prosimos e SIMOD, PR #170 che chiude anche #169).

## Punto attivo

Nessuno. **B1a e B1b sono fatti e su `main`** (PR #170, che contiene anche #169).

Prossimo: **CAL-01, calendari FUZZY di SIMOD** (richiesta di Sohayb: DeliR deve
gestire tutto). Oggi `from_prosimos.py` li rifiuta con il motivo perché l'IR non
rappresenta la disponibilità probabilistica. Primo passo: verificare nel sorgente di
Prosimos 2.1 (`scripts/fetch_datasets.py fetch prosimos`) il formato dei calendari
FUZZY e che il runner li esegua; poi IR, import, compilazione, test.

In alternativa **UX-01** (leggibilità di "Reale contro simulato").

## Ultima misura

B1b: e2e `e2e/simulation-prosimos-import.spec.ts` 8/8 (chromium e mobile-chrome),
test API 4/4, unit 4/4; gate UX in `docs/vpt/ux/b1b-server-import/`.
CONF-02: e2e `simulation-eventlog` 12/12 su chromium e mobile-chrome, axe pulito;
screenshot in `docs/vpt/ux/conformance/`. CONF-01: LoanApp 500/500 casi conformi.

## Come riprendere CAL-01

1. Leggi [`WORKFLOW.md`](./WORKFLOW.md) e la voce più recente di [`LOG.md`](./LOG.md).
2. Scarica Prosimos 2.1 (`uv run python scripts/fetch_datasets.py fetch prosimos`) e
   leggi come rappresenta ed esegue i calendari FUZZY.
3. Serve uno scenario SIMOD con calendari FUZZY scoperto sul dataset: il test di
   import e round trip va scritto per primo e deve fallire.
4. Estendi IR, `from_prosimos.py` e `compile_for_prosimos`; poi run sul runner.

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

- Impostare `DELIR_ADMIN_TOKEN` in staging e prod: senza, le cancellazioni ora
  rispondono 403 (SEC-ADMIN).
- Copiare comunque nel repo pubblico BPIC 2012/2013/2020 e Prosimos?
- Confermare le mete marcate *proposta* in `PLAN.md` (B2: scarto ≤ 10% dal paper;
  B3: gateway ±0,05, durate ±10%).
